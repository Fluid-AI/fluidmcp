import { useState, useEffect } from "react";
import { X, AlertCircle } from "lucide-react";
import * as Dialog from "@radix-ui/react-dialog";
import type { ReplicateModelConfig, ReplicateModel } from "../types/llm";

interface LLMModelFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (config: ReplicateModelConfig | Partial<ReplicateModelConfig>) => Promise<void>;
  mode: "add" | "edit";
  existingModel?: ReplicateModel;
}

export default function LLMModelForm({
  open,
  onOpenChange,
  onSubmit,
  mode,
  existingModel,
}: LLMModelFormProps) {
  const [formData, setFormData] = useState<ReplicateModelConfig>({
    model_id: "",
    type: "replicate",
    model: "",
    api_key: "${REPLICATE_API_TOKEN}",
    default_params: {
      temperature: 0.7,
      max_tokens: 1000,
    },
    timeout: 300,
    max_retries: 3,
  });

  const [showAdvanced, setShowAdvanced] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Populate form when editing
  useEffect(() => {
    if (mode === "edit" && existingModel) {
      // For edit mode, we only allow updating certain fields
      setFormData({
        model_id: existingModel.id,
        type: "replicate",
        model: existingModel.model,
        api_key: "${REPLICATE_API_TOKEN}", // Cannot edit API key
        default_params: {
          temperature: 0.7,
          max_tokens: 1000,
        },
        timeout: existingModel.timeout || 300,
        max_retries: existingModel.max_retries !== undefined ? existingModel.max_retries : 3,
      });
    } else {
      // Reset for add mode
      setFormData({
        model_id: "",
        type: "replicate",
        model: "",
        api_key: "${REPLICATE_API_TOKEN}",
        default_params: {
          temperature: 0.7,
          max_tokens: 1000,
        },
        timeout: 300,
        max_retries: 3,
      });
    }
    setErrors({});
  }, [mode, existingModel, open]);

  const validateForm = (): boolean => {
    const newErrors: Record<string, string> = {};

    // Model ID validation (only for add mode)
    if (mode === "add") {
      if (!formData.model_id.trim()) {
        newErrors.model_id = "Model ID is required";
      } else if (formData.model_id.length < 2) {
        newErrors.model_id = "Model ID must be at least 2 characters";
      } else if (!/^[a-zA-Z0-9_-]+$/.test(formData.model_id)) {
        newErrors.model_id = "Model ID can only contain alphanumeric characters, dashes, and underscores";
      }
    }

    // Model name validation (only for add mode)
    if (mode === "add") {
      if (!formData.model.trim()) {
        newErrors.model = "Model name is required";
      } else if (!/^[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+(:[a-zA-Z0-9_.-]+)?$/.test(formData.model)) {
        newErrors.model = "Model must be in format: owner/model-name or owner/model-name:version";
      }
    }

    // API key validation (only for add mode)
    if (mode === "add") {
      if (!formData.api_key.trim()) {
        newErrors.api_key = "API key is required";
      } else if (!formData.api_key.includes("$")) {
        newErrors.api_key = "API key must use environment variable syntax (e.g., ${REPLICATE_API_TOKEN})";
      }
    }

    // Timeout validation
    if (formData.timeout !== undefined && (formData.timeout < 10 || formData.timeout > 3600)) {
      newErrors.timeout = "Timeout must be between 10 and 3600 seconds";
    }

    // Max retries validation
    if (formData.max_retries !== undefined && (formData.max_retries < 0 || formData.max_retries > 10)) {
      newErrors.max_retries = "Max retries must be between 0 and 10";
    }

    // Temperature validation
    const temp = formData.default_params?.temperature;
    if (temp !== undefined && (temp < 0 || temp > 2)) {
      newErrors.temperature = "Temperature must be between 0 and 2";
    }

    // Max tokens validation
    const tokens = formData.default_params?.max_tokens;
    if (tokens !== undefined && (tokens < 1 || tokens > 100000)) {
      newErrors.max_tokens = "Max tokens must be between 1 and 100000";
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    setIsSubmitting(true);
    try {
      if (mode === "edit") {
        // For edit mode, only send updatable fields
        await onSubmit({
          default_params: formData.default_params,
          timeout: formData.timeout,
          max_retries: formData.max_retries,
        });
      } else {
        // For add mode, send full config
        await onSubmit(formData);
      }
      onOpenChange(false);
    } catch (error) {
      // Error handling is done by parent component via toast
      console.error("Form submission error:", error);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50" />
        <Dialog.Content className="fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 bg-zinc-900 border border-zinc-700 rounded-2xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto z-50">
          <div className="flex items-center justify-between mb-6">
            <Dialog.Title className="text-2xl font-bold text-white">
              {mode === "add" ? "Add LLM Model" : "Edit LLM Model"}
            </Dialog.Title>
            <Dialog.Close asChild>
              <button
                className="text-zinc-400 hover:text-white transition-colors"
                aria-label="Close"
              >
                <X className="w-5 h-5" />
              </button>
            </Dialog.Close>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Model ID (read-only in edit mode) */}
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Model ID <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={formData.model_id}
                onChange={(e) => setFormData({ ...formData, model_id: e.target.value })}
                disabled={mode === "edit"}
                placeholder="llama-2-70b"
                className={`w-full px-4 py-2 bg-zinc-800 border ${
                  errors.model_id ? "border-red-500" : "border-zinc-700"
                } rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed`}
              />
              {errors.model_id && (
                <p className="mt-1 text-sm text-red-400 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" />
                  {errors.model_id}
                </p>
              )}
              <p className="mt-1 text-xs text-zinc-500">
                Alphanumeric, dash, and underscore only. Minimum 2 characters.
              </p>
            </div>

            {/* Model Name (read-only in edit mode) */}
            <div>
              <label className="block text-sm font-medium text-zinc-300 mb-2">
                Replicate Model <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={formData.model}
                onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                disabled={mode === "edit"}
                placeholder="meta/llama-2-70b-chat"
                className={`w-full px-4 py-2 bg-zinc-800 border ${
                  errors.model ? "border-red-500" : "border-zinc-700"
                } rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed`}
              />
              {errors.model && (
                <p className="mt-1 text-sm text-red-400 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" />
                  {errors.model}
                </p>
              )}
              <p className="mt-1 text-xs text-zinc-500">
                Format: owner/model-name or owner/model-name:version
              </p>
            </div>

            {/* API Key (only in add mode) */}
            {mode === "add" && (
              <div>
                <label className="block text-sm font-medium text-zinc-300 mb-2">
                  API Key <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={formData.api_key}
                  onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                  placeholder="${REPLICATE_API_TOKEN}"
                  className={`w-full px-4 py-2 bg-zinc-800 border ${
                    errors.api_key ? "border-red-500" : "border-zinc-700"
                  } rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500 font-mono`}
                />
                {errors.api_key && (
                  <p className="mt-1 text-sm text-red-400 flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" />
                    {errors.api_key}
                  </p>
                )}
                <p className="mt-1 text-xs text-zinc-500">
                  Use environment variable syntax: $&#123;REPLICATE_API_TOKEN&#125; or $API_KEY
                </p>
              </div>
            )}

            {/* Default Parameters Section */}
            <div className="border border-zinc-700 rounded-lg p-4 bg-zinc-800/50">
              <h3 className="text-sm font-semibold text-white mb-3">Default Parameters</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-zinc-300 mb-2">
                    Temperature
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="2"
                    value={formData.default_params?.temperature ?? 0.7}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        default_params: {
                          ...formData.default_params,
                          temperature: parseFloat(e.target.value),
                        },
                      })
                    }
                    className={`w-full px-3 py-2 bg-zinc-900 border ${
                      errors.temperature ? "border-red-500" : "border-zinc-700"
                    } rounded-lg text-white text-sm focus:outline-none focus:border-indigo-500`}
                  />
                  {errors.temperature && (
                    <p className="mt-1 text-xs text-red-400">{errors.temperature}</p>
                  )}
                </div>
                <div>
                  <label className="block text-sm text-zinc-300 mb-2">
                    Max Tokens
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="100000"
                    value={formData.default_params?.max_tokens ?? 1000}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        default_params: {
                          ...formData.default_params,
                          max_tokens: parseInt(e.target.value),
                        },
                      })
                    }
                    className={`w-full px-3 py-2 bg-zinc-900 border ${
                      errors.max_tokens ? "border-red-500" : "border-zinc-700"
                    } rounded-lg text-white text-sm focus:outline-none focus:border-indigo-500`}
                  />
                  {errors.max_tokens && (
                    <p className="mt-1 text-xs text-red-400">{errors.max_tokens}</p>
                  )}
                </div>
              </div>
            </div>

            {/* Advanced Settings (collapsible) */}
            <div>
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="text-sm text-indigo-400 hover:text-indigo-300 font-medium"
              >
                {showAdvanced ? "Hide" : "Show"} Advanced Settings
              </button>

              {showAdvanced && (
                <div className="mt-4 space-y-4 p-4 border border-zinc-700 rounded-lg bg-zinc-800/50">
                  <div>
                    <label className="block text-sm text-zinc-300 mb-2">
                      Timeout (seconds)
                    </label>
                    <input
                      type="number"
                      min="10"
                      max="3600"
                      value={formData.timeout}
                      onChange={(e) =>
                        setFormData({ ...formData, timeout: parseInt(e.target.value) })
                      }
                      className={`w-full px-3 py-2 bg-zinc-900 border ${
                        errors.timeout ? "border-red-500" : "border-zinc-700"
                      } rounded-lg text-white text-sm focus:outline-none focus:border-indigo-500`}
                    />
                    {errors.timeout && (
                      <p className="mt-1 text-xs text-red-400">{errors.timeout}</p>
                    )}
                    <p className="mt-1 text-xs text-zinc-500">10-3600 seconds</p>
                  </div>
                  <div>
                    <label className="block text-sm text-zinc-300 mb-2">
                      Max Retries
                    </label>
                    <input
                      type="number"
                      min="0"
                      max="10"
                      value={formData.max_retries}
                      onChange={(e) =>
                        setFormData({ ...formData, max_retries: parseInt(e.target.value) })
                      }
                      className={`w-full px-3 py-2 bg-zinc-900 border ${
                        errors.max_retries ? "border-red-500" : "border-zinc-700"
                      } rounded-lg text-white text-sm focus:outline-none focus:border-indigo-500`}
                    />
                    {errors.max_retries && (
                      <p className="mt-1 text-xs text-red-400">{errors.max_retries}</p>
                    )}
                    <p className="mt-1 text-xs text-zinc-500">0-10 attempts</p>
                  </div>
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div className="flex gap-3 pt-4">
              <button
                type="button"
                onClick={() => onOpenChange(false)}
                disabled={isSubmitting}
                className="flex-1 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 text-white rounded-lg font-medium transition-all disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="flex-1 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-medium transition-all disabled:opacity-50"
              >
                {isSubmitting ? (mode === "add" ? "Adding..." : "Updating...") : (mode === "add" ? "Add Model" : "Update Model")}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
