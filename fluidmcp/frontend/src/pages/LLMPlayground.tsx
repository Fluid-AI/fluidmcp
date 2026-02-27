import { useState, useEffect, useRef, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { Send, Trash2, Settings, Search, RefreshCw } from "lucide-react";
import { useLLMModels } from "../hooks/useLLMModels";
import apiClient from "../services/api";
import type { ChatMessage } from "../types/llm";
import { showError } from "../services/toast";
import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";

// Preset configurations
const presets = {
  creative: { temperature: 0.9, max_tokens: 2000 },
  balanced: { temperature: 0.7, max_tokens: 1000 },
  precise: { temperature: 0.3, max_tokens: 500 }
};

// Maximum chat history to prevent memory issues
const MAX_CHAT_MESSAGES = 100;

export default function LLMPlayground() {
  const [searchParams] = useSearchParams();
  const preselectedModel = searchParams.get("model");

  const { models, refetch } = useLLMModels();
  const [lastRefreshTime, setLastRefreshTime] = useState<Date | null>(null);

  // Filter to only healthy, running models
  const availableModels = models.filter(m => m.is_running && m.is_healthy);

  // Auto-refresh model list every 30s while playground is open
  useEffect(() => {
    const refreshInterval = setInterval(async () => {
      await refetch();
      setLastRefreshTime(new Date());
    }, 30000); // 30 seconds

    return () => clearInterval(refreshInterval);
  }, [refetch]);

  const [selectedModel, setSelectedModel] = useState<string | null>(preselectedModel);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [parameters, setParameters] = useState({
    temperature: 0.7,
    max_tokens: 1000
  });
  const [preset, setPreset] = useState<'creative' | 'balanced' | 'precise'>('balanced');
  const [modelSearch, setModelSearch] = useState('');

  // Filter models based on search query (memoized to avoid recreation on every render)
  const filteredModels = useMemo(() => {
    return availableModels.filter(m =>
      m.id.toLowerCase().includes(modelSearch.toLowerCase()) ||
      (m.type && m.type.toLowerCase().includes(modelSearch.toLowerCase()))
    );
  }, [availableModels, modelSearch]);

  // CRITICAL: Ref to avoid stale closure in async operations
  const messagesRef = useRef<ChatMessage[]>([]);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Keep ref in sync with state
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  // Cleanup abort controller on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  // Auto-scroll to bottom when messages change - scroll within container, not whole page
  useEffect(() => {
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
    }
  }, [messages]);

  // CRITICAL: Sync URL param changes to state
  useEffect(() => {
    if (preselectedModel && preselectedModel !== selectedModel) {
      handleModelChange(preselectedModel);
    }
  }, [preselectedModel]);

  // Select first available model if none selected
  useEffect(() => {
    if (!selectedModel && filteredModels.length > 0) {
      setSelectedModel(filteredModels[0].id);
    }
  }, [filteredModels, selectedModel]);

  const handleModelChange = (newModelId: string) => {
    if (messages.length > 0 && newModelId !== selectedModel) {
      if (!confirm("Switching models will clear your chat history. Continue?")) {
        return;
      }
      setMessages([]);
    }
    setSelectedModel(newModelId);
  };

  const applyPreset = (presetName: keyof typeof presets) => {
    setPreset(presetName);
    setParameters(presets[presetName]);
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedModel || !input.trim() || loading) return;

    const userMessage: ChatMessage = { role: 'user', content: input.trim() };

    // Create new abort controller for this request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    // Use functional setState to avoid race conditions
    setMessages(prev => {
      const updated = [...prev, userMessage];
      // Keep only last MAX_CHAT_MESSAGES to prevent memory issues
      return updated.slice(-MAX_CHAT_MESSAGES);
    });
    setInput('');
    setLoading(true);

    try {
      // Use messagesRef.current to get fresh messages
      const currentMessages = [...messagesRef.current, userMessage];

      // Use apiClient.chatCompletion (NOT direct fetch)
      const data = await apiClient.chatCompletion({
        model: selectedModel,
        messages: currentMessages,
        temperature: parameters.temperature,
        max_tokens: parameters.max_tokens
      });

      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: data.choices[0].message.content
      };

      // Use functional setState again with history limit
      setMessages(prev => {
        const updated = [...prev, assistantMessage];
        return updated.slice(-MAX_CHAT_MESSAGES);
      });
    } catch (error) {
      // Don't show error if request was aborted (e.g., user navigated away)
      if (error instanceof Error && error.name !== 'AbortError') {
        showError(error instanceof Error ? error.message : 'Failed to send message');
        // Remove user message on error
        setMessages(prev => prev.slice(0, -1));
      }
    } finally {
      setLoading(false);
    }
  };

  const clearChat = () => {
    if (messages.length > 0 && !confirm("Clear all chat history?")) {
      return;
    }
    setMessages([]);
  };

  const selectedModelInfo = models.find(m => m.id === selectedModel);

  return (
    <div className="min-h-screen bg-black text-white flex flex-col">
      <Navbar />

      <div className="flex-1 pt-16">
        <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-8 h-full">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-full">

            {/* Left Sidebar: 25% on large screens */}
            <div className="lg:col-span-3 space-y-6">
              {/* Model Selector */}
              <div className="bg-zinc-900/90 backdrop-blur-xl border border-zinc-700/50 rounded-2xl p-6">
                <h3 className="text-lg font-semibold mb-4">Select Model</h3>

                {availableModels.length === 0 ? (
                  <div className="text-zinc-400 text-sm">
                    No healthy models available. Please start a model first.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {/* Search Input */}
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-zinc-400" />
                      <input
                        type="text"
                        value={modelSearch}
                        onChange={(e) => setModelSearch(e.target.value)}
                        placeholder="Search models..."
                        className="w-full pl-10 pr-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500"
                      />
                    </div>

                    {/* Model Dropdown */}
                    <select
                      value={selectedModel || ''}
                      onChange={(e) => handleModelChange(e.target.value)}
                      className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                    >
                      {filteredModels.length === 0 ? (
                        <option value="">No models match your search</option>
                      ) : (
                        <>
                          {/* Show selected model even if filtered out */}
                          {selectedModel && !filteredModels.find(m => m.id === selectedModel) && (
                            <option value={selectedModel}>{selectedModel} (current)</option>
                          )}
                          {filteredModels.map(m => (
                            <option key={m.id} value={m.id}>{m.id}</option>
                          ))}
                        </>
                      )}
                    </select>

                    {filteredModels.length > 0 && (
                      <div className="text-xs text-zinc-500">
                        Showing {filteredModels.length} of {availableModels.length} models
                      </div>
                    )}
                  </div>
                )}

                {/* Selected Model Info */}
                {selectedModelInfo && (
                  <div className="mt-4 p-4 bg-zinc-800/50 rounded-lg space-y-2 text-sm">
                    <div>
                      <span className="text-zinc-400">Type: </span>
                      <span className={`px-2 py-1 rounded text-xs font-medium ${
                        selectedModelInfo.type === 'process'
                          ? 'bg-blue-500/20 text-blue-400'
                          : 'bg-purple-500/20 text-purple-400'
                      }`}>
                        {selectedModelInfo.type}
                      </span>
                    </div>
                    <div>
                      <span className="text-zinc-400">Status: </span>
                      <span className={`px-2 py-1 rounded text-xs font-medium ${
                        selectedModelInfo.is_running
                          ? 'bg-green-500/20 text-green-400'
                          : 'bg-zinc-700 text-zinc-400'
                      }`}>
                        {selectedModelInfo.is_running ? 'Running' : 'Stopped'}
                      </span>
                    </div>
                    <div>
                      <span className="text-zinc-400">Health: </span>
                      <span className="text-white">{selectedModelInfo.health_message}</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Preset Buttons */}
              <div className="bg-zinc-900/90 backdrop-blur-xl border border-zinc-700/50 rounded-2xl p-6">
                <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <Settings className="w-5 h-5" />
                  Presets
                </h3>
                <div className="space-y-2">
                  <button
                    onClick={() => applyPreset('creative')}
                    className={`w-full px-4 py-3 rounded-lg font-medium transition-all text-left ${
                      preset === 'creative'
                        ? 'bg-indigo-600 text-white'
                        : 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span>🎨</span>
                      <div>
                        <div className="font-semibold">Creative</div>
                        <div className="text-xs opacity-70">temp: 0.9, tokens: 2000</div>
                      </div>
                    </div>
                  </button>
                  <button
                    onClick={() => applyPreset('balanced')}
                    className={`w-full px-4 py-3 rounded-lg font-medium transition-all text-left ${
                      preset === 'balanced'
                        ? 'bg-indigo-600 text-white'
                        : 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span>⚖️</span>
                      <div>
                        <div className="font-semibold">Balanced</div>
                        <div className="text-xs opacity-70">temp: 0.7, tokens: 1000</div>
                      </div>
                    </div>
                  </button>
                  <button
                    onClick={() => applyPreset('precise')}
                    className={`w-full px-4 py-3 rounded-lg font-medium transition-all text-left ${
                      preset === 'precise'
                        ? 'bg-indigo-600 text-white'
                        : 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      <span>🎯</span>
                      <div>
                        <div className="font-semibold">Precise</div>
                        <div className="text-xs opacity-70">temp: 0.3, tokens: 500</div>
                      </div>
                    </div>
                  </button>
                </div>
              </div>

              {/* Manual Controls */}
              <div className="bg-zinc-900/90 backdrop-blur-xl border border-zinc-700/50 rounded-2xl p-6">
                <h3 className="text-lg font-semibold mb-4">Parameters</h3>
                <div className="space-y-4">
                  <div>
                    <label className="text-sm text-zinc-400 mb-2 block">
                      Temperature: {parameters.temperature.toFixed(1)}
                    </label>
                    <input
                      type="range"
                      min="0"
                      max="2"
                      step="0.1"
                      value={parameters.temperature}
                      onChange={(e) => setParameters(prev => ({ ...prev, temperature: Number(e.target.value) }))}
                      className="w-full"
                    />
                  </div>
                  <div>
                    <label className="text-sm text-zinc-400 mb-2 block">
                      Max Tokens
                    </label>
                    <input
                      type="number"
                      min="100"
                      max="4000"
                      step="100"
                      value={parameters.max_tokens}
                      onChange={(e) => setParameters(prev => ({ ...prev, max_tokens: Number(e.target.value) }))}
                      className="w-full px-4 py-2 bg-zinc-800 border border-zinc-700 rounded-lg text-white focus:outline-none focus:border-indigo-500"
                    />
                  </div>
                </div>
              </div>

              {/* Refresh Models Button */}
              <button
                onClick={async () => {
                  await refetch();
                  setLastRefreshTime(new Date());
                }}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-medium transition-all"
              >
                <RefreshCw className="w-4 h-4" />
                Refresh Models
              </button>

              {lastRefreshTime && (
                <div className="text-xs text-zinc-500 text-center">
                  Last refresh: {lastRefreshTime.toLocaleTimeString()}
                </div>
              )}

              {/* Clear Chat Button */}
              <button
                onClick={clearChat}
                disabled={messages.length === 0}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Trash2 className="w-4 h-4" />
                Clear Chat
              </button>
            </div>

            {/* Right Content: 75% on large screens */}
            <div className="lg:col-span-9 flex flex-col h-[calc(100vh-12rem)]">
              {/* Chat Messages Container */}
              <div className="flex-1 bg-zinc-900/90 backdrop-blur-xl border border-zinc-700/50 rounded-2xl overflow-hidden flex flex-col">
                <div ref={messagesContainerRef} className="flex-1 overflow-y-auto p-6 space-y-4">
                  {messages.length === 0 ? (
                    <div className="flex items-center justify-center h-full text-center">
                      <div>
                        <div className="text-6xl mb-4">💬</div>
                        <h3 className="text-xl font-semibold mb-2">Start a Conversation</h3>
                        <p className="text-zinc-400">
                          {selectedModel
                            ? `Type a message to chat with ${selectedModel}`
                            : 'Select a model to start chatting'
                          }
                        </p>
                      </div>
                    </div>
                  ) : (
                    <>
                      {messages.map((msg, idx) => (
                        <div
                          key={idx}
                          className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                        >
                          <div
                            className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                              msg.role === 'user'
                                ? 'bg-indigo-600 text-white'
                                : 'bg-zinc-800 text-zinc-100'
                            }`}
                          >
                            <div className="text-xs opacity-70 mb-1">
                              {msg.role === 'user' ? 'You' : selectedModel}
                            </div>
                            <div className="whitespace-pre-wrap break-words">{msg.content}</div>
                          </div>
                        </div>
                      ))}
                      {loading && (
                        <div className="flex justify-start">
                          <div className="max-w-[80%] rounded-2xl px-4 py-3 bg-zinc-800 text-zinc-100">
                            <div className="text-xs opacity-70 mb-1">{selectedModel}</div>
                            <div className="flex gap-1">
                              <span className="animate-bounce">●</span>
                              <span className="animate-bounce" style={{ animationDelay: '0.1s' }}>●</span>
                              <span className="animate-bounce" style={{ animationDelay: '0.2s' }}>●</span>
                            </div>
                          </div>
                        </div>
                      )}
                    </>
                  )}
                </div>

                {/* Input Form */}
                <div className="border-t border-zinc-700/50 p-4">
                  <form onSubmit={handleSend} className="flex gap-2">
                    <textarea
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          handleSend(e);
                        }
                      }}
                      placeholder={selectedModel ? "Type your message... (Enter to send, Shift+Enter for new line)" : "Select a model first"}
                      rows={3}
                      disabled={!selectedModel || loading}
                      className="flex-1 px-4 py-3 bg-zinc-800 border border-zinc-700 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 resize-none disabled:opacity-50"
                    />
                    <button
                      type="submit"
                      disabled={!selectedModel || loading || !input.trim()}
                      className="px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                      <Send className="w-5 h-5" />
                    </button>
                  </form>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <Footer />
    </div>
  );
}
