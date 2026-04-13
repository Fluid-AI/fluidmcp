"""
DEPRECATED: run_servers.py — fmcp run is no longer supported.

fmcp serve is the only supported execution path.
All LLM state is now owned by llm_registry.py.
"""
from loguru import logger

# Re-export LLM registry accessors so any remaining callers don't break at import time.
from .llm_registry import (
    get_llm_processes,
    get_llm_health_monitor,
    register_llm_process,
)

__all__ = [
    "get_llm_processes",
    "get_llm_health_monitor",
    "register_llm_process",
]


def run_servers(*args, **kwargs):
    """Deprecated entry point — use `fmcp serve` instead."""
    raise RuntimeError(
        "'fmcp run' is deprecated and has been removed. "
        "Use 'fmcp serve' to start the FluidMCP gateway."
    )
