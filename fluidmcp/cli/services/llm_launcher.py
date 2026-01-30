"""
LLM Model Launcher for FluidMCP.

This module manages launching and lifecycle of LLM inference servers that expose
OpenAI-compatible APIs (e.g., vLLM, Ollama, LM Studio).

Includes error recovery, health checks, and automatic restart capabilities.
"""

import os
import re
import subprocess
import time
import asyncio
import httpx
from typing import Dict, Any, Optional, Tuple
from loguru import logger

# Constants
DEFAULT_SHUTDOWN_TIMEOUT = 10  # Default seconds to wait for graceful shutdown
PROCESS_START_DELAY = 0.5  # Seconds to wait for process initialization before status check
HEALTH_CHECK_TIMEOUT = 10.0  # Timeout for health check HTTP requests (seconds)
DEFAULT_MAX_RESTARTS = 3  # Default maximum restart attempts
DEFAULT_RESTART_DELAY = 5  # Default base delay between restarts (seconds)
MAX_BACKOFF_EXPONENT = 5  # Maximum exponential backoff exponent (caps at 2^5 = 32x base delay)
HEALTH_CHECK_INTERVAL = 30  # Default interval between health checks (seconds)
HEALTH_CHECK_FAILURES_THRESHOLD = 2  # Number of consecutive health check failures before restart
CUDA_OOM_CACHE_TTL = 60.0  # Cache TTL for CUDA OOM detection (seconds)

# Environment variable allowlist for subprocess
ENV_VAR_ALLOWLIST = [
    'PATH', 'HOME', 'USER', 'TMPDIR', 'LANG', 'LC_ALL',
    'CUDA_VISIBLE_DEVICES', 'CUDA_DEVICE_ORDER',
    'LD_LIBRARY_PATH', 'PYTHONPATH', 'VIRTUAL_ENV'
]


def sanitize_command_for_logging(command_parts: list) -> str:
    """
    Sanitize command arguments for safe logging.

    Redacts sensitive patterns like API keys, tokens, passwords to prevent
    credential leakage in log files.

    Args:
        command_parts: List of command arguments

    Returns:
        Sanitized command string safe for logging

    Example:
        >>> sanitize_command_for_logging(["vllm", "--api-key", "secret123"])
        'vllm --api-key ***REDACTED***'
    """
    sensitive_patterns = ['key', 'token', 'secret', 'password', 'auth', 'credential']

    safe_command = []
    redact_next = False

    for part in command_parts:
        if redact_next:
            # Previous argument indicated this value is sensitive
            safe_command.append("***REDACTED***")
            redact_next = False
        elif any(pattern in part.lower() for pattern in sensitive_patterns):
            # Check if this is key=value format
            if '=' in part:
                key, _ = part.split('=', 1)
                safe_command.append(f"{key}=***REDACTED***")
            else:
                # This is a flag like --api-key, redact next value
                safe_command.append(part)
                redact_next = True
        else:
            safe_command.append(part)

    return ' '.join(safe_command)


def filter_safe_env_vars(system_env: Dict[str, str], additional_env: Dict[str, str]) -> Dict[str, str]:
    """
    Filter system environment variables to only safe, allowlisted variables.

    This prevents accidental leakage of sensitive system environment variables
    into subprocess environments. User-provided environment variables are always
    included as they are explicitly configured.

    Args:
        system_env: System environment variables (typically os.environ)
        additional_env: User-provided environment variables from config

    Returns:
        Combined environment with only allowlisted system vars + all user vars

    Example:
        >>> filter_safe_env_vars(
        ...     {"PATH": "/usr/bin", "SECRET_KEY": "sensitive"},
        ...     {"MY_VAR": "value"}
        ... )
        {'PATH': '/usr/bin', 'MY_VAR': 'value'}  # SECRET_KEY filtered out
    """
    # Only include allowlisted system environment variables
    safe_env = {k: v for k, v in system_env.items() if k in ENV_VAR_ALLOWLIST}

    # User-provided env vars are always included (explicitly configured)
    safe_env.update(additional_env)

    return safe_env


def sanitize_model_id(model_id: str) -> str:
    """
    Sanitize model ID to prevent path traversal attacks.

    Removes or replaces characters that could be used for directory traversal
    or other malicious file system operations.

    Args:
        model_id: Raw model identifier from user input

    Returns:
        Sanitized model ID safe for use in file paths

    Examples:
        >>> sanitize_model_id("../../etc/passwd")
        '______etc_passwd'
        >>> sanitize_model_id("normal-model_123")
        'normal-model_123'
        >>> sanitize_model_id("")
        'unnamed_model'
    """
    # Replace any character that's not alphanumeric, underscore, or hyphen
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', model_id)
    # Extra safety: replace any remaining .. sequences
    sanitized = sanitized.replace('..', '_')
    # Ensure we have a non-empty result
    if not sanitized:
        sanitized = 'unnamed_model'
    return sanitized


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

        # Get and validate restart policy from config
        restart_policy = config.get("restart_policy", "no")
        if restart_policy not in ("no", "on-failure", "always"):
            raise ValueError(
                f"Invalid restart_policy '{restart_policy}' for model '{model_id}'. "
                f"Must be one of: 'no', 'on-failure', 'always'"
            )
        self.restart_policy = restart_policy

        # Validate max_restarts
        max_restarts = config.get("max_restarts", DEFAULT_MAX_RESTARTS)
        if not isinstance(max_restarts, int) or max_restarts < 0:
            raise ValueError(
                f"Invalid max_restarts {max_restarts!r} for model '{model_id}'. "
                f"Must be a non-negative integer"
            )
        self.max_restarts = max_restarts

        # Validate restart_delay
        restart_delay = config.get("restart_delay", DEFAULT_RESTART_DELAY)
        if not isinstance(restart_delay, (int, float)) or restart_delay < 0:
            raise ValueError(
                f"Invalid restart_delay {restart_delay!r} for model '{model_id}'. "
                f"Must be a non-negative number"
            )
        self.restart_delay = restart_delay

        # Health check tracking and configuration
        self.consecutive_health_failures = 0
        self.last_health_check_time: Optional[float] = None

        # Validate health_check_timeout
        health_check_timeout = config.get("health_check_timeout", HEALTH_CHECK_TIMEOUT)
        if not isinstance(health_check_timeout, (int, float)) or health_check_timeout <= 0:
            raise ValueError(
                f"Invalid health_check_timeout {health_check_timeout!r} for model '{model_id}'. "
                f"Must be a positive number"
            )
        self.health_check_timeout = health_check_timeout

        # Validate health_check_interval
        health_check_interval = config.get("health_check_interval", HEALTH_CHECK_INTERVAL)
        if not isinstance(health_check_interval, (int, float)) or health_check_interval <= 0:
            raise ValueError(
                f"Invalid health_check_interval {health_check_interval!r} for model '{model_id}'. "
                f"Must be a positive number"
            )
        self.health_check_interval = health_check_interval

        # CUDA OOM detection cache: (result, timestamp, file_mtime)
        self._cuda_oom_cache: Optional[Tuple[bool, float, Optional[float]]] = None

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
        # Security: Filter system env vars to allowlist, user env always included
        env = filter_safe_env_vars(os.environ, self.config.get("env", {}))

        full_command = [command] + args
        logger.info(f"Starting LLM model '{self.model_id}'")
        # Security: Sanitize command to prevent credential leakage in logs
        safe_command = sanitize_command_for_logging(full_command)
        logger.debug(f"Command: {safe_command}")

        # Create log file for stderr to aid debugging startup failures
        # Sanitize model_id to prevent path traversal attacks (Issue #1)
        safe_model_id = sanitize_model_id(self.model_id)
        log_dir = os.path.join(os.path.expanduser("~"), ".fluidmcp", "logs")
        os.makedirs(log_dir, exist_ok=True)
        stderr_log_path = os.path.join(log_dir, f"llm_{safe_model_id}_stderr.log")

        # Fix Issue #4: Properly handle file handle leak if Popen fails
        stderr_log = None
        try:
            # Open stderr log file for capturing process errors
            stderr_log = open(stderr_log_path, "a")
            # Security: Set restrictive permissions (owner read/write only)
            os.chmod(stderr_log_path, 0o600)

            self.process = subprocess.Popen(
                full_command,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=stderr_log,
            )

            # Store log file handle for cleanup in stop()
            self._stderr_log = stderr_log
            stderr_log = None  # Transfer ownership, don't close in finally

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
        finally:
            # Issue #4 fix: Close file handle if it wasn't transferred to self._stderr_log
            # This ensures no file handle leak if Popen fails
            if stderr_log is not None:
                stderr_log.close()

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

        async with httpx.AsyncClient(timeout=self.health_check_timeout) as client:
            for endpoint in health_endpoints:
                try:
                    response = await client.get(endpoint)
                    if response.status_code == 200:
                        self.consecutive_health_failures = 0
                        return True, None
                except Exception as e:
                    logger.debug(
                        f"Health check request to '{endpoint}' for model '{self.model_id}' failed: {e}"
                    )
                    continue

        self.consecutive_health_failures += 1
        return False, "Health check failed - no endpoints responding"

    def get_stderr_log_path(self) -> str:
        """Get the path to the stderr log file."""
        log_dir = os.path.join(os.path.expanduser("~"), ".fluidmcp", "logs")
        return os.path.join(log_dir, f"llm_{self.model_id}_stderr.log")

    def check_for_cuda_oom(self) -> bool:
        """
        Check stderr log for CUDA Out of Memory errors with caching.

        Uses caching (60s TTL) and efficient backwards file reading to minimize I/O overhead.

        Returns:
            True if CUDA OOM detected, False otherwise
        """
        log_path = self.get_stderr_log_path()
        now = time.time()

        # If log file doesn't exist, cache and return False
        if not os.path.exists(log_path):
            self._cuda_oom_cache = (False, now, None)
            return False

        # Get current modification time for cache validation
        try:
            current_mtime = os.path.getmtime(log_path)
        except OSError:
            current_mtime = None

        # Check cache: reuse recent result if file hasn't changed and TTL not expired
        if self._cuda_oom_cache is not None:
            cached_result, cached_time, cached_mtime = self._cuda_oom_cache
            if (now - cached_time) < CUDA_OOM_CACHE_TTL and cached_mtime == current_mtime:
                return cached_result

        try:
            # Efficiently read only the last ~1000 lines by seeking backwards
            max_lines = 1000
            block_size = 8192
            buffer = b""
            newline_count = 0

            with open(log_path, "rb") as f:
                f.seek(0, os.SEEK_END)
                file_size = f.tell()
                position = file_size

                while position > 0 and newline_count <= max_lines:
                    read_size = block_size if position >= block_size else position
                    position -= read_size
                    f.seek(position)
                    data = f.read(read_size)
                    buffer = data + buffer
                    newline_count = buffer.count(b"\n")

            # Decode and split into lines, then take only the last max_lines
            text = buffer.decode("utf-8", errors="ignore")
            all_lines = text.splitlines()
            recent_lines = all_lines[-max_lines:] if len(all_lines) > max_lines else all_lines

            for line in recent_lines:
                lower_line = line.lower()
                # Check for specific CUDA OOM patterns to avoid false positives
                if any(error in lower_line for error in [
                    "cuda out of memory",
                    "cudaerror: out of memory",
                    "cuda error: out of memory"
                ]):
                    self._cuda_oom_cache = (True, now, current_mtime)
                    return True

            # No CUDA OOM found; cache negative result
            self._cuda_oom_cache = (False, now, current_mtime)
        except Exception as e:
            logger.debug(f"Error reading stderr log for {self.model_id}: {e}")
            # On error, cache a negative result briefly to avoid repeated I/O failures
            self._cuda_oom_cache = (False, now, current_mtime)

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
            # Issue #6 fix: "always" restarts regardless of exit code
            if self.restart_policy == "always":
                return True

            # Issue #6 fix: "on-failure" only restarts on non-zero exit (actual failure)
            if self.restart_policy == "on-failure":
                if self.process and self.process.poll() is not None:
                    returncode = self.process.poll()
                    # Only restart on non-zero exit code (failure)
                    if returncode != 0:
                        logger.info(f"Process '{self.model_id}' exited with code {returncode}, restarting...")
                        return True
                    else:
                        logger.info(f"Process '{self.model_id}' exited cleanly (code 0), not restarting")
                        return False
                return True  # If we can't determine exit code, restart to be safe

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

            # Wait for process to stabilize
            await asyncio.sleep(2)

            if self.is_running():
                # Only increment counter after confirming success
                self.restart_count += 1
                self.last_restart_time = time.time()
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
        # Issue #5 fix: Track restarts in progress to prevent multiple simultaneous restarts
        self._restarts_in_progress: set = set()

    async def _monitor_loop(self):
        """Main monitoring loop - runs continuously until stopped."""
        logger.info(f"Health monitor started (interval: {self.check_interval}s)")

        while self._running:
            try:
                # Check health of all processes (snapshot to avoid race condition)
                for model_id, process in list(self.processes.items()):
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
                            # Issue #5 fix: Only start restart if not already in progress
                            if model_id in self._restarts_in_progress:
                                logger.debug(f"Restart already in progress for '{model_id}', skipping")
                                continue

                            logger.warning(f"LLM model '{model_id}' needs restart")

                            # Mark restart as in progress
                            self._restarts_in_progress.add(model_id)

                            try:
                                # Attempt automatic restart
                                success = await process.attempt_restart()

                                if success:
                                    logger.info(f"LLM model '{model_id}' recovered successfully")
                                else:
                                    logger.error(
                                    f"LLM model '{model_id}' failed to recover. "
                                    f"Restart count: {process.restart_count}/{process.max_restarts}"
                                )
                            finally:
                                # Issue #5 fix: Always remove from in-progress set
                                self._restarts_in_progress.discard(model_id)

                    except Exception as e:
                        logger.error(f"Error monitoring LLM model '{model_id}': {e}", exc_info=True)

                # Wait before next check
                await asyncio.sleep(self.check_interval)

            except asyncio.CancelledError:
                # Task cancellation is expected during shutdown; ignore to allow clean stop
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

        try:
            self._monitor_task = asyncio.create_task(self._monitor_loop())
            self._running = True
            logger.info("Health monitor task created")
        except RuntimeError as e:
            logger.error(f"Failed to create health monitor task (no event loop): {e}")
            raise

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
                # Task cancellation is expected during shutdown; ignore to allow clean stop
                pass

        logger.info("Health monitor stopped")

    def is_running(self) -> bool:
        """Check if the health monitor is running."""
        return self._running and self._monitor_task is not None and not self._monitor_task.done()
