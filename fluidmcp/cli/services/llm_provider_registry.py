"""
Unified LLM Provider Registry for FluidMCP.

Maps model IDs to their provider types (vllm, replicate, ollama, etc.) and
provides a unified interface for all LLM inference regardless of backend.
"""

import threading
from typing import Dict, Optional, List
from loguru import logger


# Global registry mapping model_id -> config
_llm_models_config: Dict[str, dict] = {}

# CRITICAL SECURITY FIX: Thread-safe access to _llm_models_config and _replicate_clients
# Protects against race conditions when multiple requests modify the registries concurrently
# Using RLock to allow re-entrant locking (same thread can acquire lock multiple times)
_registry_lock = threading.RLock()


def initialize_llm_registry(llm_models: Dict[str, dict]) -> None:
    """
    Initialize the LLM provider registry with configurations.

    Args:
        llm_models: Dictionary from config's "llmModels" section
                   Each entry should have a "type" field (vllm, replicate, ollama, etc.)
    """
    global _llm_models_config
    with _registry_lock:
        _llm_models_config = llm_models.copy()

        types_count = {}
        for model_id, config in llm_models.items():
            # Default to "vllm" for backward compatibility (matches get_model_type behavior)
            provider_type = config.get("type", "vllm")
            types_count[provider_type] = types_count.get(provider_type, 0) + 1

        logger.info(f"Initialized LLM registry with {len(llm_models)} models: {dict(types_count)}")


def update_model_endpoints(model_id: str, endpoints: dict) -> None:
    """
    Update runtime endpoints for a model (e.g., after vLLM infers base_url).

    Args:
        model_id: Model identifier
        endpoints: Endpoints dict to merge into model config
    """
    global _llm_models_config
    with _registry_lock:
        if model_id in _llm_models_config:
            if "endpoints" not in _llm_models_config[model_id]:
                _llm_models_config[model_id]["endpoints"] = {}
            _llm_models_config[model_id]["endpoints"].update(endpoints)
            logger.debug(f"Updated endpoints for '{model_id}': {endpoints}")
        else:
            logger.warning(f"Cannot update endpoints for unknown model '{model_id}'")


def get_model_config(model_id: str) -> Optional[dict]:
    """
    Get configuration for a specific model.

    Args:
        model_id: Model identifier

    Returns:
        Model configuration dict or None if not found
    """
    with _registry_lock:
        return _llm_models_config.get(model_id).copy() if model_id in _llm_models_config else None


def get_model_type(model_id: str) -> Optional[str]:
    """
    Get provider type for a specific model.

    Args:
        model_id: Model identifier

    Returns:
        Provider type (e.g., "vllm", "replicate", "ollama") or None if not found

    Note:
        For backward compatibility, models without explicit "type" field default to "vllm"
    """
    with _registry_lock:
        config = _llm_models_config.get(model_id)
        if config:
            # Default to "vllm" for backward compatibility with legacy configs
            return config.get("type", "vllm")
        return None


def list_models_by_type(provider_type: str) -> List[str]:
    """
    List all model IDs of a specific provider type.

    Args:
        provider_type: Provider type to filter by (e.g., "vllm", "replicate")

    Returns:
        List of model IDs

    Note:
        Uses same defaulting logic as get_model_type: missing type defaults to "vllm"
    """
    with _registry_lock:
        return [
            model_id
            for model_id, config in _llm_models_config.items()
            if config.get("type", "vllm") == provider_type
        ]


def list_all_models() -> List[dict]:
    """
    List all registered models with their types.

    Returns:
        List of dicts with model_id and type

    Note:
        Defaults to "vllm" for backward compatibility (matches get_model_type behavior)
    """
    with _registry_lock:
        return [
            {"id": model_id, "type": config.get("type", "vllm")}
            for model_id, config in _llm_models_config.items()
        ]


def clear_registry() -> None:
    """Clear the LLM registry (useful for testing)."""
    global _llm_models_config
    with _registry_lock:
        _llm_models_config.clear()
        logger.debug("Cleared LLM provider registry")
