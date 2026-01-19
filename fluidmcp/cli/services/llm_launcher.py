"""
LLM Model Launcher for FluidMCP.

This module manages launching and lifecycle of LLM inference servers that expose
OpenAI-compatible APIs (e.g., vLLM, Ollama, LM Studio).

Includes error recovery, health checks, and automatic restart capabilities.
"""

import os
import subprocess
import time
import asyncio
import httpx
from typing import Dict, Any, Optional, Tuple
from loguru import logger
from datetime import datetime

# Constants
DEFAULT_SHUTDOWN_TIMEOUT = 10  # Default seconds to wait for graceful shutdown
PROCESS_START_DELAY = 0.5  # Seconds to wait for process initialization before status check
HEALTH_CHECK_TIMEOUT = 10.0  # Timeout for health check HTTP requests (seconds)
DEFAULT_MAX_RESTARTS = 3  # Default maximum restart attempts
DEFAULT_RESTART_DELAY = 5  # Default base delay between restarts (seconds)
MAX_BACKOFF_EXPONENT = 5  # Maximum exponential backoff exponent (caps at 2^5 = 32x base delay)
HEALTH_CHECK_INTERVAL = 30  # Default interval between health checks (seconds)
HEALTH_CHECK_FAILURES_THRESHOLD = 2  # Number of consecutive health check failures before restart


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

        # Restart tracking
        self.restart_count = 0
        self.last_restart_time: Optional[float] = None
        self.start_time: Optional[float] = None

        # Get restart policy from config
        self.restart_policy = config.get("restart_policy", "no")  # no, on-failure, always
        self.max_restarts = config.get("max_restarts", DEFAULT_MAX_RESTARTS)
        self.restart_delay = config.get("restart_delay", DEFAULT_RESTART_DELAY)

        # Health check tracking
        self.consecutive_health_failures = 0
        self.last_health_check_time: Optional[float] = None

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

            # Track start time for uptime calculation
            self.start_time = time.time()

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

    def force_kill(self):
        """
        Forcefully kill the LLM process using SIGKILL.

        This is a last resort when graceful shutdown fails or the process is hung.
        """
        if not self.process:
            logger.warning(f"LLM model '{self.model_id}' process not running")
            return

        logger.warning(f"Force killing LLM model '{self.model_id}' (PID: {self.process.pid})")

        try:
            self.process.kill()
            self.process.wait(timeout=5)
            logger.info(f"LLM model '{self.model_id}' force killed successfully")
        except Exception as e:
            logger.error(f"Error force killing LLM model '{self.model_id}': {e}")
        finally:
            # Close stderr log file if it was opened
            if self._stderr_log is not None:
                try:
                    self._stderr_log.close()
                    self._stderr_log = None
                except Exception as e:
                    logger.debug(f"Error closing stderr log: {e}")

    async def check_health(self) -> Tuple[bool, Optional[str]]:
        """
        Check if the vLLM server is healthy by querying HTTP endpoints.

        Returns:
            Tuple of (is_healthy, error_message)
        """
        self.last_health_check_time = time.time()

        if not self.is_running():
            self.consecutive_health_failures += 1
            return False, "Process not running"

        # Get base URL from endpoints config
        endpoints = self.config.get("endpoints", {})
        base_url = endpoints.get("base_url")

        if not base_url:
            # No health check endpoint configured, assume healthy if process is running
            self.consecutive_health_failures = 0
            return True, None

        # Try health check endpoints
        health_endpoints = [
            f"{base_url}/health",
            f"{base_url}/v1/models",
        ]

        async with httpx.AsyncClient(timeout=HEALTH_CHECK_TIMEOUT) as client:
            for endpoint in health_endpoints:
                try:
                    response = await client.get(endpoint)
                    if response.status_code == 200:
                        self.consecutive_health_failures = 0
                        return True, None
                except Exception as e:
                    continue

        self.consecutive_health_failures += 1
        return False, "Health check failed - no endpoints responding"

    def get_stderr_log_path(self) -> str:
        """Get the path to the stderr log file."""
        log_dir = os.path.join(os.path.expanduser("~"), ".fluidmcp", "logs")
        return os.path.join(log_dir, f"llm_{self.model_id}_stderr.log")

    def check_for_cuda_oom(self) -> bool:
        """
        Check stderr log for CUDA Out of Memory errors.

        Returns:
            True if CUDA OOM detected, False otherwise
        """
        log_path = self.get_stderr_log_path()

        if not os.path.exists(log_path):
            return False

        try:
            # Read last 1000 lines to check for recent errors
            with open(log_path, 'r') as f:
                lines = f.readlines()
                recent_lines = lines[-1000:] if len(lines) > 1000 else lines

                for line in recent_lines:
                    if any(error in line.lower() for error in [
                        "cuda out of memory",
                        "cudaerror",
                        "out of memory"
                    ]):
                        return True
        except Exception as e:
            logger.debug(f"Error reading stderr log for {self.model_id}: {e}")

        return False

    def get_uptime(self) -> Optional[float]:
        """
        Get process uptime in seconds.

        Returns:
            Uptime in seconds, or None if not started
        """
        if not self.start_time:
            return None
        return time.time() - self.start_time

    def can_restart(self) -> bool:
        """
        Check if the process can be restarted based on restart policy and count.

        Returns:
            True if restart is allowed, False otherwise
        """
        if self.restart_policy == "no":
            return False

        if self.restart_count >= self.max_restarts:
            logger.warning(
                f"LLM model '{self.model_id}' has reached max restarts "
                f"({self.max_restarts}), not restarting"
            )
            return False

        return True

    def needs_restart(self) -> bool:
        """
        Check if the process needs restart based on health check failures.

        Returns:
            True if restart is needed, False otherwise
        """
        if self.restart_policy == "no":
            return False

        # Check if process is dead
        if not self.is_running():
            if self.restart_policy in ("on-failure", "always"):
                return True

        # Check if consecutive health failures exceeded threshold
        if self.consecutive_health_failures >= HEALTH_CHECK_FAILURES_THRESHOLD:
            logger.warning(
                f"LLM model '{self.model_id}' has {self.consecutive_health_failures} "
                f"consecutive health check failures (threshold: {HEALTH_CHECK_FAILURES_THRESHOLD})"
            )
            return True

        return False

    def calculate_restart_delay(self) -> float:
        """
        Calculate delay before next restart using exponential backoff.

        Returns:
            Delay in seconds
        """
        exponent = min(self.restart_count, MAX_BACKOFF_EXPONENT)
        return self.restart_delay * (2 ** exponent)

    async def attempt_restart(self) -> bool:
        """
        Attempt to restart the LLM process.

        Returns:
            True if restart successful, False otherwise
        """
        if not self.can_restart():
            return False

        logger.info(f"Attempting to restart LLM model '{self.model_id}' (attempt {self.restart_count + 1}/{self.max_restarts})")

        # Calculate delay with exponential backoff
        delay = self.calculate_restart_delay()
        logger.info(f"Waiting {delay}s before restart...")
        await asyncio.sleep(delay)

        # Stop existing process
        if self.is_running():
            self.stop()
        elif self.process:
            # Process crashed but we still have the Popen object
            self.force_kill()

        # Attempt restart
        try:
            self.start()
            self.restart_count += 1
            self.last_restart_time = time.time()

            # Wait for process to stabilize
            await asyncio.sleep(2)

            if self.is_running():
                logger.info(f"LLM model '{self.model_id}' restarted successfully")
                return True
            else:
                logger.error(f"LLM model '{self.model_id}' failed to start after restart")
                return False

        except Exception as e:
            logger.error(f"Error restarting LLM model '{self.model_id}': {e}")
            return False


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


class LLMHealthMonitor:
    """Background health monitor for LLM processes with automatic recovery."""

    def __init__(
        self,
        processes: Dict[str, LLMProcess],
        check_interval: int = HEALTH_CHECK_INTERVAL
    ):
        """
        Initialize health monitor.

        Args:
            processes: Dictionary of LLMProcess instances to monitor
            check_interval: Interval between health checks in seconds
        """
        self.processes = processes
        self.check_interval = check_interval
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

    async def _monitor_loop(self):
        """Main monitoring loop - runs continuously until stopped."""
        logger.info(f"Health monitor started (interval: {self.check_interval}s)")

        while self._running:
            try:
                # Check health of all processes
                for model_id, process in self.processes.items():
                    try:
                        # Skip if no restart policy configured
                        if process.restart_policy == "no":
                            continue

                        # Perform health check
                        is_healthy, error_msg = await process.check_health()

                        if not is_healthy:
                            logger.warning(
                                f"Health check failed for LLM model '{model_id}': {error_msg} "
                                f"(failures: {process.consecutive_health_failures})"
                            )

                            # Check for CUDA OOM errors
                            if process.check_for_cuda_oom():
                                logger.error(
                                    f"CUDA OOM detected for LLM model '{model_id}'. "
                                    "Consider reducing GPU memory utilization or using a smaller model."
                                )

                        # Check if restart is needed
                        if process.needs_restart():
                            logger.warning(f"LLM model '{model_id}' needs restart")

                            # Attempt automatic restart
                            success = await process.attempt_restart()

                            if success:
                                logger.info(f"LLM model '{model_id}' recovered successfully")
                            else:
                                logger.error(
                                    f"LLM model '{model_id}' failed to recover. "
                                    f"Restart count: {process.restart_count}/{process.max_restarts}"
                                )

                    except Exception as e:
                        logger.error(f"Error monitoring LLM model '{model_id}': {e}", exc_info=True)

                # Wait before next check
                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                logger.info("Health monitor cancelled")
                break
            except Exception as e:
                logger.error(f"Error in health monitor loop: {e}", exc_info=True)
                await asyncio.sleep(self.check_interval)

        logger.info("Health monitor stopped")

    def start(self):
        """Start the background health monitor."""
        if self._running:
            logger.warning("Health monitor already running")
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Health monitor task created")

    async def stop(self):
        """Stop the background health monitor."""
        if not self._running:
            return

        logger.info("Stopping health monitor...")
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("Health monitor stopped")

    def is_running(self) -> bool:
        """Check if the health monitor is running."""
        return self._running and self._monitor_task is not None and not self._monitor_task.done()
