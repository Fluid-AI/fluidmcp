"""
LLM process registry — single source of truth for LLM runtime state.

Pre-microservice boundary for the future LLM Inference Service.
All serve-mode LLM operations read/write through this module.
"""
import threading
from typing import Dict, Optional
from loguru import logger

from .llm_launcher import LLMProcess, LLMHealthMonitor

# ── State ──────────────────────────────────────────────────────
_llm_processes: Dict[str, LLMProcess] = {}
_llm_endpoints: Dict[str, Dict[str, str]] = {}
_llm_health_monitor: Optional[LLMHealthMonitor] = None
_registry_lock = threading.Lock()


# ── Getters / setters ──────────────────────────────────────────
def get_llm_processes() -> Dict[str, LLMProcess]:
    return _llm_processes


def get_llm_endpoints() -> Dict[str, Dict[str, str]]:
    return _llm_endpoints


def get_llm_health_monitor() -> Optional[LLMHealthMonitor]:
    return _llm_health_monitor


def set_llm_health_monitor(monitor: Optional[LLMHealthMonitor]) -> None:
    global _llm_health_monitor
    _llm_health_monitor = monitor


def register_llm_process(model_id: str, process: LLMProcess) -> None:
    with _registry_lock:
        _llm_processes[model_id] = process
        logger.info(f"Registered LLM process: {model_id}")


def unregister_llm_process(model_id: str) -> None:
    with _registry_lock:
        _llm_processes.pop(model_id, None)


def register_llm_endpoint(model_id: str, endpoints: Dict[str, str]) -> None:
    with _registry_lock:
        _llm_endpoints[model_id] = endpoints


# ── Health monitor startup ─────────────────────────────────────
async def start_llm_health_monitor_if_needed() -> None:
    """
    Start LLM health monitor if any registered processes have restart policies.
    Called from server.py after models are loaded from persistence.
    """
    global _llm_health_monitor

    processes_with_restart = {
        mid: p for mid, p in _llm_processes.items()
        if p.restart_policy != "no"
    }
    if not processes_with_restart:
        return

    if _llm_health_monitor and _llm_health_monitor.is_running():
        await _llm_health_monitor.stop()

    _llm_health_monitor = LLMHealthMonitor(processes_with_restart)
    _llm_health_monitor.start()
    logger.info(f"LLM health monitor started ({len(processes_with_restart)} process(es))")


# ── Cleanup ────────────────────────────────────────────────────
def cleanup_llm_state() -> None:
    """Stop health monitor and all LLM processes. Called from atexit/shutdown."""
    global _llm_health_monitor

    monitor = _llm_health_monitor
    if monitor and monitor.is_running():
        monitor._running = False
        _llm_health_monitor = None

    if _llm_processes:
        from .llm_launcher import stop_all_llm_models
        stop_all_llm_models(_llm_processes)
        _llm_processes.clear()
