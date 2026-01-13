"""
LLM Model Launcher for FluidMCP.

This module manages launching and lifecycle of LLM inference servers that expose
OpenAI-compatible APIs (e.g., vLLM, Ollama, LM Studio).
"""

import os
import subprocess
import time
from typing import Dict, Any, Optional
from loguru import logger

# Constants
DEFAULT_SHUTDOWN_TIMEOUT = 10  # Default seconds to wait for graceful shutdown
PROCESS_START_DELAY = 0.5  # Seconds to wait for process initialization before status check


class LLMProcess:
    """Manages a single LLM inference server process."""

    def __init__(self, model_id: str, config: Dict[str, Any]):
        """
        Initialize LLM process manager.

        Args:
            model_id: Unique identifier for this LLM model
            config: Configuration dict with command, args, env, endpoints
        """
        self.model_id = model_id
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self._stderr_log: Optional[object] = None  # File handle for stderr logging

    def start(self) -> subprocess.Popen:
        """
        Start the LLM server as a subprocess.

        Returns:
            The subprocess.Popen instance

        Raises:
            ValueError: If command is missing from config
        """
        if "command" not in self.config:
            raise ValueError(f"LLM model '{self.model_id}' missing 'command' in config")

        command = self.config["command"]
        args = self.config.get("args", [])
        env = {**os.environ, **self.config.get("env", {})}

        full_command = [command] + args
        logger.info(f"Starting LLM model '{self.model_id}'")
        logger.debug(f"Command: {' '.join(full_command)}")

        # Create log file for stderr to aid debugging startup failures
        log_dir = os.path.join(os.path.expanduser("~"), ".fluidmcp", "logs")
        os.makedirs(log_dir, exist_ok=True)
        stderr_log_path = os.path.join(log_dir, f"llm_{self.model_id}_stderr.log")

        try:
            # Open stderr log file for capturing process errors
            stderr_log = open(stderr_log_path, "a")

            self.process = subprocess.Popen(
                full_command,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=stderr_log,
            )

            # Store log file handle for cleanup in stop()
            self._stderr_log = stderr_log

            logger.info(f"LLM model '{self.model_id}' started (PID: {self.process.pid})")
            logger.debug(f"Stderr log: {stderr_log_path}")
            return self.process

        except FileNotFoundError:
            logger.error(f"Command '{command}' not found. Is {command} installed?")
            raise
        except Exception as e:
            logger.error(f"Failed to start LLM model '{self.model_id}': {e}")
            raise

    def stop(self, timeout: Optional[int] = None):
        """
        Stop the LLM server gracefully.

        Args:
            timeout: Seconds to wait for graceful shutdown before force kill.
                If None, uses model config 'shutdown_timeout' or DEFAULT_SHUTDOWN_TIMEOUT.
        """
        # Determine effective timeout: explicit arg > model config > default
        if timeout is None:
            timeout = self.config.get("shutdown_timeout", DEFAULT_SHUTDOWN_TIMEOUT)
        if not self.process:
            logger.warning(f"LLM model '{self.model_id}' process not running")
            return

        logger.info(f"Stopping LLM model '{self.model_id}' (PID: {self.process.pid})")

        try:
            self.process.terminate()
            self.process.wait(timeout=timeout)
            logger.info(f"LLM model '{self.model_id}' stopped gracefully")
        except subprocess.TimeoutExpired:
            logger.warning(f"LLM model '{self.model_id}' did not stop gracefully, forcing kill")
            self.process.kill()
            self.process.wait()
            logger.info(f"LLM model '{self.model_id}' force killed")
        finally:
            # Close stderr log file if it was opened
            if self._stderr_log is not None:
                try:
                    self._stderr_log.close()
                    self._stderr_log = None
                except Exception as e:
                    logger.debug(f"Error closing stderr log: {e}")

    def is_running(self) -> bool:
        """Check if the LLM process is still running."""
        if not self.process:
            return False
        return self.process.poll() is None


def launch_llm_models(llm_config: Dict[str, Any]) -> Dict[str, LLMProcess]:
    """
    Launch all configured LLM models.

    Args:
        llm_config: Dictionary mapping model IDs to their configurations

    Returns:
        Dictionary mapping model IDs to LLMProcess instances

    Example:
        llm_config = {
            "vllm": {
                "command": "vllm",
                "args": ["serve", "facebook/opt-125m", "--port", "8001"],
                "env": {},
                "endpoints": {"base_url": "http://localhost:8001/v1"}
            }
        }
        processes = launch_llm_models(llm_config)
    """
    if not llm_config:
        logger.debug("No LLM models configured")
        return {}

    processes = {}
    logger.info(f"Launching {len(llm_config)} LLM model(s)...")

    for model_id, config in llm_config.items():
        try:
            process = LLMProcess(model_id, config)
            process.start()

            # Brief delay to allow process to initialize before checking status
            time.sleep(PROCESS_START_DELAY)

            if not process.is_running():
                logger.error(f"LLM model '{model_id}' failed to start")
                # Don't add failed processes to the dictionary
            else:
                # Only add successfully running processes
                processes[model_id] = process
                logger.info(f"✓ LLM model '{model_id}' is running")

        except Exception as e:
            logger.error(f"Failed to launch LLM model '{model_id}': {e}")
            # Continue launching other models even if one fails
            continue

    return processes


def stop_all_llm_models(processes: Dict[str, LLMProcess]):
    """
    Stop all running LLM model processes.

    Args:
        processes: Dictionary of LLMProcess instances to stop
    """
    if not processes:
        return

    logger.info(f"Stopping {len(processes)} LLM model(s)...")

    for model_id, process in processes.items():
        try:
            process.stop()
        except Exception as e:
            logger.error(f"Error stopping LLM model '{model_id}': {e}")
