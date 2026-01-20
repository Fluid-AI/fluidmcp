import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiClient } from '../services/api';
import { useToolRunner } from '../hooks/useToolRunner';
import { JsonSchemaForm } from '../components/form/JsonSchemaForm';
import { ToolResult } from '../components/result/ToolResult';
import type { Server, Tool } from '../types/server';
import './ToolRunner.css';

export const ToolRunner: React.FC = () => {
  const { serverId, toolName } = useParams<{ serverId: string; toolName: string }>();
  const navigate = useNavigate();

  const [server, setServer] = useState<Server | null>(null);
  const [tool, setTool] = useState<Tool | null>(null);
  const [loadingServer, setLoadingServer] = useState(true);
  const [loadingError, setLoadingError] = useState<string | null>(null);
  const [formValues, setFormValues] = useState<Record<string, any> | undefined>(undefined);

  const {
    execute,
    result,
    error: executionError,
    loading: executing,
    executionTime,
    history,
    loadFromHistory,
    clearHistory,
  } = useToolRunner(serverId || '', server?.name || '', toolName || '');

  // Load server and tool details on mount
  useEffect(() => {
    if (!serverId || !toolName) {
      setLoadingError('Invalid server or tool name');
      setLoadingServer(false);
      return;
    }

    let isMounted = true;

    const loadServerAndTool = async () => {
      try {
        if (isMounted) {
          setLoadingServer(true);
          setLoadingError(null);
        }

        // Fetch server details
        const serverDetails = await apiClient.getServerDetails(serverId);

        if (!isMounted) return;
        setServer(serverDetails as Server);

        // Fetch tools for this server
        const toolsResponse = await apiClient.getServerTools(serverId);

        if (!isMounted) return;
        const foundTool = toolsResponse.tools.find((t) => t.name === toolName);

        if (!foundTool) {
          if (isMounted) {
            setLoadingError(`Tool "${toolName}" not found on server "${serverDetails.name}"`);
          }
          return;
        }

        if (isMounted) {
          setTool(foundTool);
        }
      } catch (err: any) {
        if (isMounted) {
          setLoadingError(err.message || 'Failed to load server or tool details');
        }
      } finally {
        if (isMounted) {
          setLoadingServer(false);
        }
      }
    };

    loadServerAndTool();

    return () => {
      isMounted = false;
    };
  }, [serverId, toolName]);

  const handleSubmit = async (values: Record<string, any>) => {
    await execute(values);
  };

  const handleLoadFromHistory = (executionId: string) => {
    const args = loadFromHistory(executionId);
    if (args) {
      setFormValues(args);
    }
  };

  const handleClearHistory = () => {
    if (window.confirm('Are you sure you want to clear the execution history for this tool?')) {
      clearHistory();
    }
  };

  // Loading state
  if (loadingServer) {
    return (
      <div className="tool-runner-container">
        <div className="loading">Loading tool details...</div>
      </div>
    );
  }

  // Error state
  if (loadingError || !server || !tool) {
    return (
      <div className="tool-runner-container">
        <div className="error-box">
          <h2>Error</h2>
          <p>{loadingError || 'Failed to load server or tool'}</p>
          <button onClick={() => navigate('/dashboard')} className="btn-secondary">
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="tool-runner-container">
      {/* Header */}
      <div className="tool-runner-header">
        <div className="breadcrumb">
          <span className="breadcrumb-item" onClick={() => navigate('/dashboard')}>
            Dashboard
          </span>
          <span className="breadcrumb-separator">&gt;</span>
          <span
            className="breadcrumb-item"
            onClick={() => navigate(`/servers/${serverId}`)}
          >
            {server.name}
          </span>
          <span className="breadcrumb-separator">&gt;</span>
          <span className="breadcrumb-item active">{tool.name}</span>
        </div>

        <h1>{tool.name}</h1>
        {tool.description && <p className="tool-description">{tool.description}</p>}
      </div>

      {/* Main Content */}
      <div className="tool-runner-content">
        {/* Left Column: Form and History */}
        <div className="tool-runner-left">
          {/* Parameters Form */}
          <div className="tool-runner-section">
            <h2>Parameters</h2>
            {tool.inputSchema ? (
              <JsonSchemaForm
                schema={tool.inputSchema}
                initialValues={formValues}
                onSubmit={handleSubmit}
                submitLabel="Run Tool"
                loading={executing}
              />
            ) : (
              <div className="no-parameters">
                <p>This tool has no parameters</p>
                <button
                  onClick={() => handleSubmit({})}
                  disabled={executing}
                  className="btn-primary"
                >
                  {executing ? 'Running...' : 'Run Tool'}
                </button>
              </div>
            )}
          </div>

          {/* Execution History */}
          {history.length > 0 && (
            <div className="tool-runner-section">
              <div className="section-header">
                <h2>Execution History</h2>
                <button onClick={handleClearHistory} className="btn-text">
                  Clear All
                </button>
              </div>

              <div className="history-list">
                {history.slice(0, 10).map((execution) => (
                  <div
                    key={execution.id}
                    className={`history-item ${execution.success ? 'success' : 'failed'}`}
                  >
                    <div className="history-item-header">
                      <span className="history-timestamp">
                        {new Date(execution.timestamp).toLocaleString()}
                      </span>
                      <span className={`history-status ${execution.success ? 'success' : 'failed'}`}>
                        {execution.success ? '✓' : '✗'}
                      </span>
                    </div>

                    <div className="history-item-details">
                      <pre className="history-args">
                        {JSON.stringify(execution.arguments, null, 2)}
                      </pre>
                    </div>

                    <button
                      onClick={() => handleLoadFromHistory(execution.id)}
                      className="btn-load-history"
                    >
                      Load
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Results */}
        {(result !== null || executionError) && (
          <div className="tool-runner-right">
            <ToolResult
              result={result}
              error={executionError || undefined}
              loading={executing}
              executionTime={executionTime}
            />
          </div>
        )}
      </div>
    </div>
  );
};
