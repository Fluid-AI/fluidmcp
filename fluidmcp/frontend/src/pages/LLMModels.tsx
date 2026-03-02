import React, { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import LLMModelCard from "../components/LLMModelCard";
import LLMModelForm from "../components/LLMModelForm";
import { LLMListControls } from "../components/LLMListControls";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { Pagination } from "../components/Pagination";
import ErrorMessage from "../components/ErrorMessage";
import { useLLMModels } from "../hooks/useLLMModels";
import { useDebounce } from "../hooks/useDebounce";
import { showSuccess, showError, showLoading } from "../services/toast";
import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";
import { Skeleton } from "@/components/ui/skeleton";
import { Plus, MessageSquare } from "lucide-react";
import AOS from 'aos';
import 'aos/dist/aos.css';
import apiClient from "../services/api";
import type { ReplicateModelConfig, ReplicateModel } from "../types/llm";

export default function LLMModels() {
  const navigate = useNavigate();
  const { models, loading, error, refetch } = useLLMModels();

  // Controls state
  const [searchQuery, setSearchQuery] = useState("");
  const debouncedSearchQuery = useDebounce(searchQuery, 300);
  const [sortBy, setSortBy] = useState<'name-asc' | 'name-desc' | 'health' | 'uptime'>('name-asc');
  const [filterBy, setFilterBy] = useState<'all' | 'running' | 'stopped' | 'healthy' | 'unhealthy' | 'process' | 'replicate'>('all');

  // Modal state for add/edit
  const [modalState, setModalState] = useState<{
    open: boolean;
    mode: 'add' | 'edit';
    model?: ReplicateModel;
  }>({ open: false, mode: 'add' });

  // Filtering, sorting, searching logic (memoized)
  const filteredModels = useMemo(() => {
    return models
      .filter(model => {
        if (filterBy === 'running') return model.is_running;
        if (filterBy === 'stopped') return !model.is_running;
        if (filterBy === 'healthy') return model.is_healthy && model.is_running;
        if (filterBy === 'unhealthy') return !model.is_healthy && model.is_running;
        if (filterBy === 'process') return model.type === 'process';
        if (filterBy === 'replicate') return model.type === 'replicate';
        return true;
      })
      .filter(model => model.id.toLowerCase().includes(debouncedSearchQuery.toLowerCase()));
  }, [models, filterBy, debouncedSearchQuery]);

  const sortedModels = [...filteredModels].sort((a, b) => {
    if (sortBy === 'name-asc') return a.id.localeCompare(b.id);
    if (sortBy === 'name-desc') return b.id.localeCompare(a.id);
    if (sortBy === 'health') {
      const healthScore = (m: typeof a) => m.is_running ? (m.is_healthy ? 2 : 1) : 0;
      return healthScore(b) - healthScore(a);
    }
    if (sortBy === 'uptime') {
      const getUptime = (m: typeof a) => {
        if (m.type === 'process') return m.uptime_seconds || 0;
        return 0;
      };
      return getUptime(b) - getUptime(a);
    }
    return 0;
  });

  // Pagination logic
  const itemsPerPage = 9;
  const [currentPage, setCurrentPage] = useState(1);
  const totalPages = Math.ceil(sortedModels.length / itemsPerPage);
  const paginatedModels = sortedModels.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  // Ref for model list section
  const modelListRef = React.useRef<HTMLDivElement>(null);

  // Scroll to model list on page change
  const handlePageChange = (page: number) => {
    setCurrentPage(page);
    setTimeout(() => {
      modelListRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 0);
  };

  // Reset to page 1 if filters/search/sort change and currentPage is out of range
  useEffect(() => {
    if (currentPage > totalPages && totalPages > 0) setCurrentPage(1);
  }, [searchQuery, sortBy, filterBy, sortedModels.length, currentPage, totalPages]);

  const handleClearFilters = () => {
    setSearchQuery("");
    setSortBy('name-asc');
    setFilterBy('all');
  };

  useEffect(() => {
    AOS.init({
      duration: 800,
      easing: 'ease-in-out',
      once: true,
      offset: 50,
    });
  }, []);

  // --- Action Handlers ---

  const handleCreateModel = async (config: ReplicateModelConfig | Partial<ReplicateModelConfig>) => {
    const toastId = showLoading('Creating model...');
    try {
      await apiClient.createLLMModel(config as ReplicateModelConfig);
      showSuccess('Model created successfully', toastId);
      refetch();
    } catch (err) {
      showError(`Failed to create model: ${err instanceof Error ? err.message : 'Unknown error'}`, toastId);
      throw err;
    }
  };

  const handleUpdateModel = async (modelId: string, updates: Partial<ReplicateModelConfig>) => {
    const toastId = showLoading('Updating model...');
    try {
      await apiClient.updateLLMModel(modelId, updates);
      showSuccess('Model updated successfully', toastId);
      refetch();
    } catch (err) {
      showError(`Failed to update model: ${err instanceof Error ? err.message : 'Unknown error'}`, toastId);
      throw err;
    }
  };

  const handleOpenAddModal = () => {
    setModalState({ open: true, mode: 'add' });
  };

  const handleFormSubmit = async (config: ReplicateModelConfig | Partial<ReplicateModelConfig>) => {
    if (modalState.mode === 'add') {
      await handleCreateModel(config);
    } else if (modalState.mode === 'edit' && modalState.model) {
      await handleUpdateModel(modalState.model.id, config);
    }
  };

  // --- Header button style (matches Dashboard refresh button pattern) ---
  const headerBtnStyle: React.CSSProperties = {
    background: 'transparent',
    color: '#d1d5db',
    border: '1px solid rgba(63, 63, 70, 0.6)',
    padding: '0.5rem 1rem',
    borderRadius: '0.375rem',
    fontSize: '0.875rem',
    fontWeight: '500',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '0.5rem',
    transition: 'all 0.2s',
    margin: 0,
    cursor: 'pointer',
  };
  const headerBtnHoverIn = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.currentTarget.style.background = 'rgba(39, 39, 42, 0.8)';
    e.currentTarget.style.borderColor = 'rgba(82, 82, 91, 0.8)';
  };
  const headerBtnHoverOut = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.currentTarget.style.background = 'transparent';
    e.currentTarget.style.borderColor = 'rgba(63, 63, 70, 0.6)';
  };

  // --- Loading State (matches Dashboard skeleton) ---
  if (loading && models.length === 0) {
    return (
      <div className="dashboard">
        <Navbar />
        <div style={{ paddingTop: '64px' }}>
          <header className="dashboard-header">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <Skeleton className="h-8 w-64 mb-2" />
                <Skeleton className="h-4 w-48" />
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <Skeleton className="h-10 w-28" />
                <Skeleton className="h-10 w-24" />
                <Skeleton className="h-10 w-24" />
              </div>
            </div>
          </header>

          <section className="dashboard-section">
            <Skeleton className="h-6 w-56 mb-6" />
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {[...Array(6)].map((_, index) => (
                <div key={index} className="relative bg-gradient-to-br from-zinc-900/90 to-zinc-800/90 backdrop-blur-xl border border-zinc-700/50 rounded-2xl p-6">
                  <div className="flex items-start justify-between mb-4">
                    <Skeleton className="h-6 w-40" />
                    <Skeleton className="h-5 w-16 rounded-full" />
                  </div>
                  <Skeleton className="h-4 w-full mb-2" />
                  <Skeleton className="h-4 w-3/4 mb-4" />
                  <div className="flex items-center gap-4 mb-4">
                    <Skeleton className="h-4 w-20" />
                    <Skeleton className="h-4 w-32" />
                  </div>
                  <div className="flex items-center gap-2 pt-4 border-t border-zinc-700/50">
                    <Skeleton className="h-10 flex-1" />
                    <Skeleton className="h-10 flex-1" />
                  </div>
                </div>
              ))}
            </div>
          </section>

          <Footer />
        </div>
      </div>
    );
  }

  // --- Error State (matches Dashboard) ---
  if (error) {
    return (
      <div className="dashboard">
        <Navbar />
        <div style={{ paddingTop: '64px' }}>
          <ErrorMessage message={error} onRetry={refetch} />
        </div>
      </div>
    );
  }

  // --- Stats ---
  const runningCount = models.filter(m => m.is_running).length;
  const healthyCount = models.filter(m => m.is_healthy).length;

  // --- Main Render (matches Dashboard structure exactly) ---
  return (
    <div className="dashboard">
      <Navbar />

      {/* Header */}
      <div style={{ paddingTop: '64px' }}>
        <header className="dashboard-header">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <h1>LLM Models</h1>
              <p className="subtitle">
                {models.length} {models.length === 1 ? 'model' : 'models'} configured, {runningCount} running, {healthyCount} healthy
              </p>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
              <button onClick={handleOpenAddModal} style={headerBtnStyle} onMouseEnter={headerBtnHoverIn} onMouseLeave={headerBtnHoverOut}>
                <Plus className="w-4 h-4" />
                Add Model
              </button>
              <button onClick={() => navigate('/llm/playground')} style={headerBtnStyle} onMouseEnter={headerBtnHoverIn} onMouseLeave={headerBtnHoverOut}>
                <MessageSquare className="w-4 h-4" />
                Try LLMs
              </button>
              <button onClick={refetch} style={headerBtnStyle} onMouseEnter={headerBtnHoverIn} onMouseLeave={headerBtnHoverOut}>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Refresh
              </button>
            </div>
          </div>
        </header>
      </div>

      {/* Main content */}
      <ErrorBoundary fallback={
        <div className="dashboard-section">
          <h2>LLM Models</h2>
          <div className="result-error">
            <h3>Error Loading Models</h3>
            <p>Failed to render model list. Please refresh the page.</p>
          </div>
        </div>
      }>
        <section className="dashboard-section">
          <h2 ref={modelListRef}>Currently configured models</h2>

          <div style={{ marginBottom: 24 }}>
            <LLMListControls
              searchQuery={searchQuery}
              onSearchChange={setSearchQuery}
              sortBy={sortBy}
              onSortChange={v => setSortBy(v as any)}
              filterBy={filterBy}
              onFilterChange={v => setFilterBy(v as any)}
              onClearFilters={handleClearFilters}
            />
          </div>

          {sortedModels.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">🤖</div>
              <h3 className="empty-state-title">No models found</h3>
              <p className="empty-state-description">
                Try adjusting your search, sort, or filter options.
              </p>
            </div>
          ) : (
            <>
              <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                {paginatedModels.map((model, index) => (
                  <div
                    key={model.id}
                    data-aos="fade-up"
                    data-aos-delay={index * 100}
                  >
                    <LLMModelCard
                      model={model}
                      onQuickTry={() => navigate(`/llm/playground?model=${model.id}`)}
                      onViewDetails={() => navigate(`/llm/models/${model.id}`)}
                    />
                  </div>
                ))}
              </div>
              {sortedModels.length > itemsPerPage && (
                <div style={{ marginTop: 32 }}>
                  <Pagination
                    currentPage={currentPage}
                    totalPages={totalPages}
                    totalItems={sortedModels.length}
                    itemsPerPage={itemsPerPage}
                    onPageChange={handlePageChange}
                    itemName="models"
                  />
                </div>
              )}
            </>
          )}
        </section>
      </ErrorBoundary>

      {/* Footer */}
      <Footer />

      {/* Add/Edit Model Modal */}
      <LLMModelForm
        open={modalState.open}
        onOpenChange={(open) => setModalState({ ...modalState, open })}
        onSubmit={handleFormSubmit}
        mode={modalState.mode}
        existingModel={modalState.model}
      />
    </div>
  );
}
