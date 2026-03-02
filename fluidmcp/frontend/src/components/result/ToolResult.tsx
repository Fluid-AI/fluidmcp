import React, { useState } from 'react';
import { ResultActions } from './ResultActions';
import { JsonResultView } from './JsonResultView';
import { TextResultView } from './TextResultView';
import { TableResultView } from './TableResultView';
import { McpContentView } from './McpContentView';
import { ErrorBoundary } from '../ErrorBoundary';
import { showError } from '../../services/toast';

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
  const [viewMode, setViewMode] = useState<'formatted' | 'raw'>('formatted');

  const handleCopy = () => {
    try {
      const textToCopy = viewMode === 'raw' 
        ? JSON.stringify(result, null, 2)
        : extractCopyText(result, format);
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
      showError('Failed to download result. It may contain circular references.');
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: '600' }}>Results</h2>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          {result !== null && !error && (
            <>
              {/* View Mode Toggle */}
              <div style={{ 
                display: 'flex', 
                background: 'rgba(0, 0, 0, 0.3)', 
                borderRadius: '0.375rem',
                padding: '0.25rem',
                gap: '0.25rem'
              }}>
                <button
                  onClick={() => setViewMode('formatted')}
                  style={{
                    padding: '0.375rem 0.75rem',
                    borderRadius: '0.25rem',
                    border: 'none',
                    fontSize: '0.875rem',
                    fontWeight: '500',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    background: viewMode === 'formatted' ? '#fff' : 'transparent',
                    color: viewMode === 'formatted' ? '#000' : 'rgba(255, 255, 255, 0.7)'
                  }}
                >
                  Formatted
                </button>
                <button
                  onClick={() => setViewMode('raw')}
                  style={{
                    padding: '0.375rem 0.75rem',
                    borderRadius: '0.25rem',
                    border: 'none',
                    fontSize: '0.875rem',
                    fontWeight: '500',
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    background: viewMode === 'raw' ? '#fff' : 'transparent',
                    color: viewMode === 'raw' ? '#000' : 'rgba(255, 255, 255, 0.7)'
                  }}
                >
                  Raw JSON
                </button>
              </div>
              
              <ResultActions
                onCopy={handleCopy}
                onDownload={handleDownload}
                canExpand={format === ResultFormat.JSON_OBJECT && viewMode === 'formatted'}
                isExpanded={expandAll}
                onToggleExpand={() => setExpandAll(!expandAll)}
              />
            </>
          )}
        </div>
      </div>

      {/* Execution Info */}
      {executionTime !== null && executionTime !== undefined && (
        <div style={{ 
          padding: '0.5rem 1rem',
          background: 'rgba(99, 102, 241, 0.1)',
          border: '1px solid rgba(99, 102, 241, 0.3)',
          borderRadius: '0.5rem',
          fontSize: '0.875rem'
        }}>
          <span style={{ color: 'rgba(255, 255, 255, 0.7)' }}>
            Execution Time: <strong style={{ color: '#fff' }}>{executionTime.toFixed(2)}s</strong>
          </span>
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div style={{
          padding: '1rem',
          background: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: '0.5rem'
        }}>
          <h3 style={{ color: '#ef4444', marginBottom: '0.5rem' }}>Error</h3>
          <p style={{ color: 'rgba(255, 255, 255, 0.9)' }}>{error}</p>
        </div>
      )}

      {/* Result Display */}
      {!error && result !== null && (
        <div style={{
          background: 'rgba(0, 0, 0, 0.3)',
          border: '1px solid rgba(63, 63, 70, 0.5)',
          borderRadius: '0.5rem',
          padding: '1.5rem',
          maxHeight: '70vh',
          overflow: 'auto'
        }}>
          {viewMode === 'raw' ? (
            <pre style={{ 
              margin: 0, 
              color: '#e5e7eb',
              fontSize: '0.95rem',
              lineHeight: '1.8',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              fontFamily: 'ui-monospace, monospace'
            }}>
              {JSON.stringify(result, null, 2)}
            </pre>
          ) : (
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
                <ErrorBoundary>
                  <TableResultView data={result as Array<Record<string, unknown>>} />
                </ErrorBoundary>
              )}
              {format === ResultFormat.JSON_OBJECT && (
                <ErrorBoundary>
                  <JsonResultView data={result} expandAll={expandAll} />
                </ErrorBoundary>
              )}
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
      )}
    </div>
  );
};
