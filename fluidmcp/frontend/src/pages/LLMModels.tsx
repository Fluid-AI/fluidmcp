import React, { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import LLMModelRow from "../components/LLMModelRow";
import LLMModelForm from "../components/LLMModelForm";
import { Pagination } from "../components/Pagination";
import ErrorMessage from "../components/ErrorMessage";
import { useLLMModels } from "../hooks/useLLMModels";
import { useDebounce } from "../hooks/useDebounce";
import { showSuccess, showError, showLoading } from "../services/toast";
import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";
import { Skeleton } from "@/components/ui/skeleton";
import { Search, Filter, RefreshCw, MessageSquare, Plus } from "lucide-react";
import AOS from 'aos';
import 'aos/dist/aos.css';
import apiClient from "../services/api";
import type { ReplicateModelConfig, ReplicateModel } from "../types/llm";

export default function LLMModels() {
  const navigate = useNavigate();
  const { models, loading, error, refetch, restartModel, stopModel, triggerHealthCheck } = useLLMModels();

  // Controls state
  const [searchQuery, setSearchQuery] = useState("");
  const debouncedSearchQuery = useDebounce(searchQuery, 300);
  const [sortBy, setSortBy] = useState<'name-asc' | 'name-desc' | 'health' | 'uptime'>('name-asc');
  const [filterBy, setFilterBy] = useState<'all' | 'running' | 'stopped' | 'healthy' | 'unhealthy' | 'process' | 'replicate'>('all');

  // Action state
  const [actionState, setActionState] = useState<{
    modelId: string | null;
    type: 'restarting' | 'stopping' | null;
  }>({ modelId: null, type: null });

  // Modal state for add/edit
  const [modalState, setModalState] = useState<{
    open: boolean;
    mode: 'add' | 'edit';
    model?: ReplicateModel;
  }>({ open: false, mode: 'add' });

  // Filtering, sorting, searching logic (memoized to prevent unnecessary recalculations)
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

  const handleRestartModel = async (modelId: string) => {
    if (actionState.type !== null) return;

    const model = models.find(m => m.id === modelId);
    const modelName = model?.id || modelId;

    setActionState({ modelId, type: 'restarting' });
    const toastId = showLoading(`Restarting ${modelName}...`);

    try {
      await restartModel(modelId);
      showSuccess(`${modelName} restarted successfully`, toastId);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      showError(`Failed to restart ${modelName}: ${message}`, toastId);
    } finally {
      setActionState({ modelId: null, type: null });
    }
  };

  const handleStopModel = async (modelId: string) => {
    if (actionState.type !== null) return;

    const model = models.find(m => m.id === modelId);
    const modelName = model?.id || modelId;

    setActionState({ modelId, type: 'stopping' });
    const toastId = showLoading(`Stopping ${modelName}...`);

    try {
      await stopModel(modelId);
      showSuccess(`${modelName} stopped successfully`, toastId);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      showError(`Failed to stop ${modelName}: ${message}`, toastId);
    } finally {
      setActionState({ modelId: null, type: null });
    }
  };

  const handleHealthCheck = async (modelId: string) => {
    if (actionState.type !== null) return;

    const model = models.find(m => m.id === modelId);
    const modelName = model?.id || modelId;

    setActionState({ modelId, type: 'health-checking' as any });
    const toastId = showLoading(`Checking health of ${modelName}...`);

    try {
      await triggerHealthCheck(modelId);
      showSuccess(`Health check completed for ${modelName}`, toastId);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      showError(`Failed to check health of ${modelName}: ${message}`, toastId);
    } finally {
      setActionState({ modelId: null, type: null });
    }
  };

  const handleCreateModel = async (config: ReplicateModelConfig | Partial<ReplicateModelConfig>) => {
    const toastId = showLoading('Creating model...');
    try {
      await apiClient.createLLMModel(config as ReplicateModelConfig);
      showSuccess('Model created successfully', toastId);
      refetch(); // Refresh the models list
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      showError(`Failed to create model: ${message}`, toastId);
      throw err; // Re-throw so form knows it failed
    }
  };

  const handleUpdateModel = async (modelId: string, updates: Partial<ReplicateModelConfig>) => {
    const toastId = showLoading('Updating model...');
    try {
      await apiClient.updateLLMModel(modelId, updates);
      showSuccess('Model updated successfully', toastId);
      refetch(); // Refresh the models list
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      showError(`Failed to update model: ${message}`, toastId);
      throw err; // Re-throw so form knows it failed
    }
  };

  const handleDeleteModel = async (modelId: string) => {
    const model = models.find(m => m.id === modelId);
    const modelName = model?.id || modelId;

    if (!confirm(`Are you sure you want to delete ${modelName}? This action cannot be undone.`)) {
      return;
    }

    const toastId = showLoading(`Deleting ${modelName}...`);
    try {
      await apiClient.deleteLLMModel(modelId);
      showSuccess(`${modelName} deleted successfully`, toastId);
      refetch(); // Refresh the models list
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      showError(`Failed to delete ${modelName}: ${message}`, toastId);
    }
  };

  const handleOpenAddModal = () => {
    setModalState({ open: true, mode: 'add' });
  };

  const handleOpenEditModal = (model: ReplicateModel) => {
    setModalState({ open: true, mode: 'edit', model });
  };

  const handleFormSubmit = async (config: ReplicateModelConfig | Partial<ReplicateModelConfig>) => {
    if (modalState.mode === 'add') {
      await handleCreateModel(config);
    } else if (modalState.mode === 'edit' && modalState.model) {
      await handleUpdateModel(modalState.model.id, config);
    }
  };

  if (error) {
    return (
      <div className="min-h-screen bg-black text-white">
        <Navbar />
        <div className="flex items-center justify-center p-4 pt-32">
          <ErrorMessage message={error} />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black text-white">
      <Navbar />

      {/* Hero Section */}
      <div className="relative overflow-hidden pt-16">
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-500/10 via-purple-500/10 to-pink-500/10" />
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
          <div className="text-center" data-aos="fade-up">
            <h1 className="text-4xl md:text-5xl font-bold mb-4 bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400 text-transparent bg-clip-text">
              LLM Models
            </h1>
            <p className="text-xl text-zinc-400 mb-8 max-w-3xl mx-auto">
              Manage your local and cloud-based LLM inference models
            </p>
          </div>

          {/* Stats Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-12" data-aos="fade-up" data-aos-delay="100">
            <div className="bg-zinc-900/50 backdrop-blur-xl border border-zinc-800 rounded-xl p-4">
              <div className="text-2xl font-bold text-white">{models.length}</div>
              <div className="text-sm text-zinc-400">Total Models</div>
            </div>
            <div className="bg-zinc-900/50 backdrop-blur-xl border border-zinc-800 rounded-xl p-4">
              <div className="text-2xl font-bold text-green-400">{models.filter(m => m.is_running).length}</div>
              <div className="text-sm text-zinc-400">Running</div>
            </div>
            <div className="bg-zinc-900/50 backdrop-blur-xl border border-zinc-800 rounded-xl p-4">
              <div className="text-2xl font-bold text-blue-400">{models.filter(m => m.is_healthy).length}</div>
              <div className="text-sm text-zinc-400">Healthy</div>
            </div>
            <div className="bg-zinc-900/50 backdrop-blur-xl border border-zinc-800 rounded-xl p-4">
              <div className="text-2xl font-bold text-purple-400">{models.filter(m => m.type === 'replicate').length}</div>
              <div className="text-sm text-zinc-400">Cloud Models</div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="mt-8 flex justify-center gap-4" data-aos="fade-up" data-aos-delay="200">
            <button
              onClick={handleOpenAddModal}
              className="flex items-center gap-2 px-6 py-3 bg-green-600 hover:bg-green-700 text-white rounded-lg font-semibold transition-all duration-200 shadow-lg hover:shadow-green-500/50"
            >
              <Plus className="w-5 h-5" />
              Add LLM Model
            </button>
            <button
              onClick={() => navigate('/llm/playground')}
              className="flex items-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-semibold transition-all duration-200 shadow-lg hover:shadow-indigo-500/50"
            >
              <MessageSquare className="w-5 h-5" />
              Try the llms
            </button>
          </div>
        </div>
      </div>

      {/* Controls Section */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8" ref={modelListRef}>
        <div className="flex flex-col lg:flex-row gap-4 mb-8" data-aos="fade-up">
          {/* Search */}
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-400" />
            <input
              type="text"
              placeholder="Search models..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-zinc-900 border border-zinc-800 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500"
            />
          </div>

          {/* Filter */}
          <div className="relative">
            <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-400" />
            <select
              value={filterBy}
              onChange={(e) => setFilterBy(e.target.value as any)}
              className="pl-10 pr-8 py-2 bg-zinc-900 border border-zinc-800 rounded-lg text-white focus:outline-none focus:border-indigo-500 appearance-none cursor-pointer"
            >
              <option value="all">All Models</option>
              <option value="running">Running</option>
              <option value="stopped">Stopped</option>
              <option value="healthy">Healthy</option>
              <option value="unhealthy">Unhealthy</option>
              <option value="process">Local Process</option>
              <option value="replicate">Cloud (Replicate)</option>
            </select>
          </div>

          {/* Sort */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as any)}
            className="px-4 py-2 bg-zinc-900 border border-zinc-800 rounded-lg text-white focus:outline-none focus:border-indigo-500 cursor-pointer"
          >
            <option value="name-asc">Name (A-Z)</option>
            <option value="name-desc">Name (Z-A)</option>
            <option value="health">Health Status</option>
            <option value="uptime">Uptime</option>
          </select>

          {/* Refresh */}
          <button
            onClick={() => refetch()}
            disabled={loading}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-medium transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>

          {/* Clear Filters */}
          {(searchQuery || filterBy !== 'all' || sortBy !== 'name-asc') && (
            <button
              onClick={handleClearFilters}
              className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg font-medium transition-all duration-200"
            >
              Clear
            </button>
          )}
        </div>

        {/* Models List */}
        {loading && models.length === 0 ? (
          <div className="flex flex-col gap-4">
            {[...Array(6)].map((_, i) => (
              <Skeleton key={i} className="h-32 rounded-2xl bg-zinc-900" />
            ))}
          </div>
        ) : paginatedModels.length === 0 ? (
          <div className="text-center py-16" data-aos="fade-up">
            <p className="text-zinc-400 text-lg">No models found</p>
            {(searchQuery || filterBy !== 'all') && (
              <button
                onClick={handleClearFilters}
                className="mt-4 px-6 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-medium transition-all duration-200"
              >
                Clear Filters
              </button>
            )}
          </div>
        ) : (
          <>
            <div className="flex flex-col gap-4" data-aos="fade-up">
              {paginatedModels.map((model, index) => (
                <div key={model.id} data-aos="fade-up" data-aos-delay={index * 50}>
                  <LLMModelRow
                    model={model}
                    onRestart={handleRestartModel}
                    onStop={handleStopModel}
                    onHealthCheck={handleHealthCheck}
                    onEdit={handleOpenEditModal}
                    onDelete={handleDeleteModel}
                    isPerformingAction={actionState.modelId === model.id && actionState.type !== null}
                  />
                </div>
              ))}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="mt-8" data-aos="fade-up">
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
      </div>

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
