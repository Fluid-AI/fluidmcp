import React, { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { apiClient } from '../services/api';
import { useToolRunner } from '../hooks/useToolRunner';
import { JsonSchemaForm } from '../components/form/JsonSchemaForm';
import { ToolResult } from '../components/result/ToolResult';
import { ErrorBoundary } from '../components/ErrorBoundary';
import type { Server, Tool } from '../types/server';
import { Footer } from '@/components/Footer';
import { Skeleton } from '@/components/ui/skeleton';

export const ToolRunner: React.FC = () => {
  const { serverId, toolName } = useParams<{ serverId: string; toolName: string }>();
  const navigate = useNavigate();

  const [server, setServer] = useState<Server | null>(null);
  const [tool, setTool] = useState<Tool | null>(null);
  const [loadingServer, setLoadingServer] = useState(true);
  const [loadingError, setLoadingError] = useState<string | null>(null);
  const [formValues, setFormValues] = useState<Record<string, any> | undefined>(undefined);
  const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false);

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
      <div className="dashboard" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        {/* Navbar */}
        <header className="fixed top-0 left-0 right-0 z-50 border-b border-border/40 bg-background/95 backdrop-blur-md supports-[backdrop-filter]:bg-background/60 transition-all duration-200">
          <div className="container mx-auto flex h-16 max-w-screen-xl items-center justify-between px-6">
            <div className="flex items-center space-x-8">
              <Link to="/" className="flex items-center space-x-2 group transition-all duration-200 hover:scale-105">
                <span className="text-lg font-bold bg-gradient-to-r from-foreground to-foreground/80 bg-clip-text whitespace-nowrap">Fluid MCP </span>
              </Link>
              <nav className="hidden md:flex items-center space-x-1 text-sm">
                <Link 
                  to="/servers" 
                  className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground"
                >
                  Servers
                </Link>
                <Link
                  to="/status"
                  className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground/60"
                >
                  Status
                </Link>
                <Link
                  to="/documentation"
                  className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground/60"
                >
                  Documentation
                </Link>
              </nav>
            </div>
            <div className="flex items-center space-x-3">
              <button 
                style={{ background: '#000', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', transition: 'all 0.2s', margin: 0 }}
                onMouseEnter={(e) => e.currentTarget.style.background = '#18181b'}
                onMouseLeave={(e) => e.currentTarget.style.background = '#000'}
              >
                <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
                Fluid MCP for your Enterprise
              </button>
              <button 
                style={{ background: '#000', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', transition: 'all 0.2s', margin: 0 }}
                onMouseEnter={(e) => e.currentTarget.style.background = '#18181b'}
                onMouseLeave={(e) => e.currentTarget.style.background = '#000'}
              >
                <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
                </svg>
                Report Issue
              </button>
            </div>
          </div>
        </header>
        <div style={{ paddingTop: '64px', flex: 1 }}>
          <header className="dashboard-header">
            <Skeleton className="h-8 w-64 mb-4" />
            <Skeleton className="h-6 w-96 mb-2" />
          </header>
          <section className="dashboard-section">
            <Skeleton className="h-96 w-full" />
          </section>
        </div>
        <Footer />
      </div>
    );
  }

  // Error state
  if (loadingError || !server || !tool) {
    return (
      <div className="dashboard" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
        {/* Navbar */}
        <header className="fixed top-0 left-0 right-0 z-50 border-b border-border/40 bg-background/95 backdrop-blur-md supports-[backdrop-filter]:bg-background/60 transition-all duration-200">
          <div className="container mx-auto flex h-16 max-w-screen-xl items-center justify-between px-6">
            <div className="flex items-center space-x-8">
              <Link to="/" className="flex items-center space-x-2 group transition-all duration-200 hover:scale-105">
                <span className="text-lg font-bold bg-gradient-to-r from-foreground to-foreground/80 bg-clip-text whitespace-nowrap">Fluid MCP </span>
              </Link>
              <nav className="hidden md:flex items-center space-x-1 text-sm">
                <Link 
                  to="/servers" 
                  className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground"
                >
                  Servers
                </Link>
                <Link
                  to="/status"
                  className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground/60"
                >
                  Status
                </Link>
                <Link
                  to="/documentation"
                  className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground/60"
                >
                  Documentation
                </Link>
              </nav>
            </div>
            <div className="flex items-center space-x-3">
              <button 
                style={{ background: '#000', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', transition: 'all 0.2s', margin: 0 }}
                onMouseEnter={(e) => e.currentTarget.style.background = '#18181b'}
                onMouseLeave={(e) => e.currentTarget.style.background = '#000'}
              >
                <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
                </svg>
                Fluid MCP for your Enterprise
              </button>
              <button 
                style={{ background: '#000', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', transition: 'all 0.2s', margin: 0 }}
                onMouseEnter={(e) => e.currentTarget.style.background = '#18181b'}
                onMouseLeave={(e) => e.currentTarget.style.background = '#000'}
              >
                <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
                </svg>
                Report Issue
              </button>
            </div>
          </div>
        </header>
        <div style={{ paddingTop: '64px', flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
          <div className="error-box" style={{ maxWidth: '600px', margin: '0 auto', padding: '2rem', textAlign: 'center' }}>
            <h2>Error</h2>
            <p>{loadingError || 'Failed to load server or tool'}</p>
            <button 
              onClick={() => navigate('/servers')} 
              className="px-4 py-2 bg-white hover:bg-zinc-100 text-black rounded-lg font-medium transition-all duration-200 mt-4"
            >
              Back to Servers
            </button>
          </div>
        </div>
        <Footer />
      </div>
    );
  }

  return (
    <div className="dashboard" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* Navbar */}
      <header className="fixed top-0 left-0 right-0 z-50 border-b border-border/40 bg-background/95 backdrop-blur-md supports-[backdrop-filter]:bg-background/60 transition-all duration-200">
        <div className="container mx-auto flex h-16 max-w-screen-xl items-center justify-between px-6">
          <div className="flex items-center space-x-8">
            <Link to="/" className="flex items-center space-x-2 group transition-all duration-200 hover:scale-105">
              <span className="text-lg font-bold bg-gradient-to-r from-foreground to-foreground/80 bg-clip-text whitespace-nowrap">Fluid MCP </span>
            </Link>
            <nav className="hidden md:flex items-center space-x-1 text-sm">
              <Link 
                to="/servers" 
                className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground"
              >
                Servers
              </Link>
              <Link 
                to="/status" 
                className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground/60"
              >
                Status
              </Link>
              <Link
                to="/documentation"
                className="inline-flex h-10 items-center justify-center rounded-md px-4 py-2 text-sm font-medium transition-all duration-200 hover:bg-zinc-800 hover:text-white focus:bg-zinc-800 focus:text-white focus:outline-none text-foreground/60"
              >
                Documentation
              </Link>
            </nav>
          </div>
          <div className="flex items-center space-x-3">
            <button 
              style={{ background: '#000', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', transition: 'all 0.2s', margin: 0 }}
              onMouseEnter={(e) => e.currentTarget.style.background = '#18181b'}
              onMouseLeave={(e) => e.currentTarget.style.background = '#000'}
            >
              <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
              </svg>
              Fluid MCP for your Enterprise
            </button>
            <button 
              style={{ background: '#000', color: '#fff', border: 'none', padding: '0.5rem 1rem', borderRadius: '0.375rem', fontSize: '0.875rem', fontWeight: '500', display: 'inline-flex', alignItems: 'center', transition: 'all 0.2s', margin: 0 }}
              onMouseEnter={(e) => e.currentTarget.style.background = '#18181b'}
              onMouseLeave={(e) => e.currentTarget.style.background = '#000'}
            >
              <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
              </svg>
              Report Issue
            </button>
          </div>
        </div>
      </header>

      <div style={{ paddingTop: '64px', flex: 1 }}>
        <div style={{ 
          maxWidth: (result !== null || executionError) ? '1600px' : '900px', 
          margin: '0 auto', 
          padding: '2rem',
          transition: 'max-width 0.3s ease'
        }}>
          {/* Breadcrumb */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem', fontSize: '0.875rem', color: 'rgba(255, 255, 255, 0.6)' }}>
            <span 
              onClick={() => navigate('/servers')} 
              style={{ cursor: 'pointer', transition: 'color 0.2s' }}
              onMouseEnter={(e) => e.currentTarget.style.color = '#fff'}
              onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(255, 255, 255, 0.6)'}
            >
              Servers
            </span>
            <span>&gt;</span>
            <span
              onClick={() => navigate(`/servers/${serverId}`)}
              style={{ cursor: 'pointer', transition: 'color 0.2s' }}
              onMouseEnter={(e) => e.currentTarget.style.color = '#fff'}
              onMouseLeave={(e) => e.currentTarget.style.color = 'rgba(255, 255, 255, 0.6)'}
            >
              {server.name}
            </span>
            <span>&gt;</span>
            <span style={{ color: '#fff' }}>{tool.name}</span>
          </div>

          {/* Page Header */}
          <div style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <h1 style={{ fontSize: '2rem', fontWeight: 'bold', marginBottom: '0.5rem' }}>{tool.name}</h1>
              {tool.description && (
                <p style={{ color: 'rgba(255, 255, 255, 0.6)', fontSize: '1rem' }}>{tool.description}</p>
              )}
            </div>
            {history.length > 0 && (
              <button
                onClick={() => setHistoryDrawerOpen(true)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.75rem 1.25rem',
                  background: 'linear-gradient(to right, rgba(99, 102, 241, 0.15), rgba(139, 92, 246, 0.15))',
                  border: '1px solid rgba(99, 102, 241, 0.3)',
                  borderRadius: '0.5rem',
                  color: '#fff',
                  fontSize: '0.9rem',
                  fontWeight: '600',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  whiteSpace: 'nowrap'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'linear-gradient(to right, rgba(99, 102, 241, 0.25), rgba(139, 92, 246, 0.25))';
                  e.currentTarget.style.transform = 'translateY(-2px)';
                  e.currentTarget.style.boxShadow = '0 4px 12px rgba(99, 102, 241, 0.3)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'linear-gradient(to right, rgba(99, 102, 241, 0.15), rgba(139, 92, 246, 0.15))';
                  e.currentTarget.style.transform = 'translateY(0)';
                  e.currentTarget.style.boxShadow = 'none';
                }}
              >
                <span style={{ fontSize: '1.25rem' }}>📜</span>
                <span>Execution History</span>
                <span style={{
                  padding: '0.125rem 0.5rem',
                  background: 'rgba(99, 102, 241, 0.3)',
                  borderRadius: '0.75rem',
                  fontSize: '0.75rem'
                }}>
                  {history.length}
                </span>
              </button>
            )}
          </div>

      {/* Main Content */}
      <ErrorBoundary fallback={
        <div className="tool-runner-content">
          <div className="result-error">
            <h3>Error Loading Tool</h3>
            <p>Failed to render tool execution interface. Please try again.</p>
            <button onClick={() => navigate('/dashboard')} className="btn-secondary">
              Back to Dashboard
            </button>
          </div>
        </div>
      }>
        <div style={{
          display: (result !== null || executionError) ? 'grid' : 'block',
          gridTemplateColumns: (result !== null || executionError) ? '2fr 3fr' : undefined,
          gap: '2rem',
          marginBottom: '2rem'
        }}>
        {/* Left Column: Form and History */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', width: '100%' }}>
          {/* Parameters Form */}
          <div style={{ 
            background: 'linear-gradient(to bottom right, rgba(39, 39, 42, 0.9), rgba(24, 24, 27, 0.9))',
            border: '1px solid rgba(63, 63, 70, 0.5)',
            borderRadius: '0.75rem',
            padding: '1.5rem',
            width: '100%'
          }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: '600', marginBottom: '1rem' }}>Parameters</h2>
            {tool.inputSchema ? (
              <JsonSchemaForm
                schema={tool.inputSchema}
                initialValues={formValues}
                onSubmit={handleSubmit}
                submitLabel="Run Tool"
                loading={executing}
              />
            ) : (
              <div style={{ textAlign: 'center', padding: '2rem' }}>
                <p style={{ marginBottom: '1rem', color: 'rgba(255, 255, 255, 0.6)' }}>This tool has no parameters</p>
                <button
                  onClick={() => handleSubmit({})}
                  disabled={executing}
                  className="px-6 py-2 bg-white hover:bg-zinc-100 text-black rounded-lg font-medium transition-all duration-200"
                >
                  {executing ? 'Running...' : 'Run Tool'}
                </button>
              </div>
            )}
          </div>


        </div>

        {/* Right Column: Results */}
        {(result !== null || executionError) && (
          <div style={{ 
            background: 'linear-gradient(to bottom right, rgba(39, 39, 42, 0.9), rgba(24, 24, 27, 0.9))',
            border: '1px solid rgba(63, 63, 70, 0.5)',
            borderRadius: '0.75rem',
            padding: '1.5rem',
            height: 'fit-content'
          }}>
            <ToolResult
              result={result}
              error={executionError || undefined}
              loading={executing}
              executionTime={executionTime}
            />
          </div>
        )}
        </div>
      </ErrorBoundary>
        </div>
      </div>

      {/* Execution History Drawer */}
      {historyDrawerOpen && (
        <>
          {/* Overlay */}
          <div 
            onClick={() => setHistoryDrawerOpen(false)}
            style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: 'rgba(0, 0, 0, 0.5)',
              zIndex: 999,
              animation: 'fadeIn 0.2s ease-out'
            }}
          />
          
          {/* Drawer */}
          <div style={{
            position: 'fixed',
            top: 0,
            right: 0,
            bottom: 0,
            width: '500px',
            maxWidth: '90vw',
            background: '#09090b',
            borderLeft: '1px solid rgba(63, 63, 70, 0.5)',
            boxShadow: '-8px 0 32px rgba(0, 0, 0, 0.6)',
            zIndex: 1000,
            display: 'flex',
            flexDirection: 'column',
            animation: 'slideInRight 0.3s ease-out'
          }}>
            {/* Drawer Header */}
            <div style={{
              padding: '1.5rem',
              borderBottom: '1px solid rgba(63, 63, 70, 0.5)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              background: 'linear-gradient(to bottom, rgba(39, 39, 42, 0.8), rgba(24, 24, 27, 0.8))'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span style={{ fontSize: '1.5rem' }}>📜</span>
                <div>
                  <h2 style={{ fontSize: '1.25rem', fontWeight: '600', margin: 0 }}>Execution History</h2>
                  <p style={{ fontSize: '0.8rem', color: 'rgba(255, 255, 255, 0.6)', margin: '0.25rem 0 0 0' }}>
                    {history.length} run{history.length !== 1 ? 's' : ''}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setHistoryDrawerOpen(false)}
                style={{
                  background: 'rgba(63, 63, 70, 0.5)',
                  border: '1px solid rgba(63, 63, 70, 0.7)',
                  borderRadius: '0.5rem',
                  padding: '0.5rem',
                  cursor: 'pointer',
                  color: '#fff',
                  fontSize: '1.25rem',
                  width: '2.5rem',
                  height: '2.5rem',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  transition: 'all 0.2s'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(63, 63, 70, 0.8)';
                  e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.3)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(63, 63, 70, 0.5)';
                  e.currentTarget.style.borderColor = 'rgba(63, 63, 70, 0.7)';
                }}
              >
                ✕
              </button>
            </div>

            {/* Clear All Button */}
            <div style={{ padding: '1rem 1.5rem', borderBottom: '1px solid rgba(63, 63, 70, 0.3)', background: 'rgba(24, 24, 27, 0.5)' }}>
              <button 
                onClick={handleClearHistory}
                style={{ 
                  width: '100%',
                  padding: '0.75rem 1rem', 
                  background: 'rgba(239, 68, 68, 0.1)', 
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  borderRadius: '0.5rem',
                  color: '#fca5a5',
                  fontSize: '0.875rem',
                  fontWeight: '600',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '0.5rem'
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = 'rgba(239, 68, 68, 0.15)';
                  e.currentTarget.style.borderColor = 'rgba(239, 68, 68, 0.5)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)';
                  e.currentTarget.style.borderColor = 'rgba(239, 68, 68, 0.3)';
                }}
              >
                <span>🗑️</span>
                Clear All History
              </button>
            </div>

            {/* Drawer Content */}
            <div style={{ 
              flex: 1, 
              overflowY: 'auto',
              padding: '1rem 1.5rem',
              background: '#09090b'
            }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {history.slice(0, 20).map((execution) => (
                  <div
                    key={execution.id}
                    style={{
                      background: execution.success 
                        ? 'linear-gradient(to right, rgba(34, 197, 94, 0.1), rgba(34, 197, 94, 0.05))'
                        : 'linear-gradient(to right, rgba(239, 68, 68, 0.1), rgba(239, 68, 68, 0.05))',
                      border: `1px solid ${execution.success ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
                      borderLeft: `3px solid ${execution.success ? '#22c55e' : '#ef4444'}`,
                      borderRadius: '0.5rem',
                      padding: '1rem',
                      transition: 'all 0.2s'
                    }}
                  >
                    {/* Header with timestamp and status */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span style={{ fontSize: '1rem' }}>🕐</span>
                        <span style={{ fontSize: '0.8rem', color: 'rgba(255, 255, 255, 0.7)', fontWeight: '500' }}>
                          {new Date(execution.timestamp).toLocaleString('en-US', {
                            month: 'short',
                            day: 'numeric',
                            hour: '2-digit',
                            minute: '2-digit'
                          })}
                        </span>
                      </div>
                      <div style={{ 
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.375rem',
                        padding: '0.25rem 0.75rem',
                        background: execution.success ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                        borderRadius: '1rem',
                        fontSize: '0.75rem',
                        fontWeight: '600',
                        color: execution.success ? '#86efac' : '#fca5a5'
                      }}>
                        {execution.success ? '✓ Success' : '✗ Failed'}
                      </div>
                    </div>

                    {/* Parameters preview */}
                    <div style={{ marginBottom: '0.75rem' }}>
                      <div style={{ 
                        fontSize: '0.75rem', 
                        color: 'rgba(255, 255, 255, 0.5)', 
                        marginBottom: '0.5rem',
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                        fontWeight: '600'
                      }}>
                        Parameters
                      </div>
                      <div style={{ 
                        background: 'rgba(0, 0, 0, 0.25)',
                        padding: '0.75rem',
                        borderRadius: '0.375rem',
                        border: '1px solid rgba(255, 255, 255, 0.05)'
                      }}>
                        <pre style={{ 
                          margin: 0,
                          fontSize: '0.8rem',
                          overflow: 'auto',
                          maxHeight: '120px',
                          color: '#e5e7eb',
                          lineHeight: '1.5'
                        }}>
                          {JSON.stringify(execution.arguments, null, 2)}
                        </pre>
                      </div>
                    </div>

                    {/* Action button */}
                    <button
                      onClick={() => {
                        handleLoadFromHistory(execution.id);
                        setHistoryDrawerOpen(false);
                      }}
                      style={{
                        width: '100%',
                        padding: '0.625rem 1rem',
                        background: '#fff',
                        color: '#000',
                        border: 'none',
                        borderRadius: '0.375rem',
                        fontSize: '0.875rem',
                        fontWeight: '600',
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '0.5rem'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = '#f4f4f5';
                        e.currentTarget.style.transform = 'scale(1.02)';
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = '#fff';
                        e.currentTarget.style.transform = 'scale(1)';
                      }}
                    >
                      <span>↻</span>
                      Load Parameters
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <style>{`
            @keyframes fadeIn {
              from { opacity: 0; }
              to { opacity: 1; }
            }
            @keyframes slideInRight {
              from { transform: translateX(100%); }
              to { transform: translateX(0); }
            }
          `}</style>
        </>
      )}

      <Footer />
    </div>
  );
};
