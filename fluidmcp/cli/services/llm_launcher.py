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

        try:
            self.process = subprocess.Popen(
                full_command,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            logger.info(f"LLM model '{self.model_id}' started (PID: {self.process.pid})")
            return self.process

        except FileNotFoundError:
            logger.error(f"Command '{command}' not found. Is {command} installed?")
            raise
        except Exception as e:
            logger.error(f"Failed to start LLM model '{self.model_id}': {e}")
            raise

    def stop(self, timeout: int = 10):
        """
        Stop the LLM server gracefully.

        Args:
            timeout: Seconds to wait for graceful shutdown before force kill
        """
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
            processes[model_id] = process

            # Small delay to allow process to start
            time.sleep(0.5)

            if not process.is_running():
                logger.error(f"LLM model '{model_id}' failed to start")
            else:
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
