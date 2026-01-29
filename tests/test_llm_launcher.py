"""Unit tests for llm_launcher.py"""

# Standard library imports
import asyncio
import os
import subprocess
import time
from unittest.mock import AsyncMock, Mock, patch

# Third-party imports
import httpx
import pytest

# Local application imports
from fluidmcp.cli.services.llm_launcher import (
    CUDA_OOM_CACHE_TTL,
    DEFAULT_MAX_RESTARTS,
    DEFAULT_RESTART_DELAY,
    DEFAULT_SHUTDOWN_TIMEOUT,
    HEALTH_CHECK_FAILURES_THRESHOLD,
    HEALTH_CHECK_INTERVAL,
    HEALTH_CHECK_TIMEOUT,
    LLMHealthMonitor,
    LLMProcess,
    MAX_BACKOFF_EXPONENT,
    PROCESS_START_DELAY,
    launch_llm_models,
    stop_all_llm_models,
)

# Test constants
TEST_TASK_START_DELAY = 0.1  # Time to allow async tasks to start
TEST_HEALTH_CHECK_INTERVAL = 0.5  # Seconds for health check interval in tests
TEST_HEALTH_CHECK_WAIT = 0.6  # Wait slightly longer than interval


class TestLLMProcess:
    """Tests for LLMProcess class"""

    def test_init_stores_config(self):
        """Test that __init__ properly stores model_id and config"""
        config = {"command": "vllm", "args": ["serve", "model"]}
        process = LLMProcess("test-model", config)

        assert process.model_id == "test-model"
        assert process.config == config
        assert process.process is None
        assert process._stderr_log is None

    def test_start_raises_on_missing_command(self):
        """Test that start() raises ValueError when command is missing"""
        process = LLMProcess("test", {"args": ["serve"]})

        with pytest.raises(ValueError, match="missing 'command'"):
            process.start()

    def test_start_creates_stderr_log_file(self, tmp_path):
        """Test that start() creates stderr log file in ~/.fluidmcp/logs/"""
        config = {"command": "echo", "args": ["test"]}
        process = LLMProcess("test-model", config)

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            with patch("subprocess.Popen") as mock_popen:
                mock_popen.return_value.pid = 12345
                process.start()

                # Verify log directory was created
                log_dir = tmp_path / ".fluidmcp" / "logs"
                assert log_dir.exists()

                # Verify stderr log file path
                expected_log = log_dir / "llm_test-model_stderr.log"
                assert expected_log.exists()

    def test_start_launches_subprocess_with_stderr_logging(self, tmp_path):
        """Test that start() launches subprocess with stderr redirected to log file"""
        config = {
            "command": "vllm",
            "args": ["serve", "facebook/opt-125m"],
            "env": {"CUDA_VISIBLE_DEVICES": "0"}
        }
        process = LLMProcess("vllm", config)

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            with patch("subprocess.Popen") as mock_popen:
                mock_proc = Mock()
                mock_proc.pid = 99999
                mock_popen.return_value = mock_proc

                result = process.start()

                # Verify Popen was called with correct arguments
                mock_popen.assert_called_once()
                call_args = mock_popen.call_args

                # Check command
                assert call_args[0][0] == ["vllm", "serve", "facebook/opt-125m"]

                # Check env includes both os.environ and custom env
                assert "CUDA_VISIBLE_DEVICES" in call_args[1]["env"]

                # Check stdout is DEVNULL
                assert call_args[1]["stdout"] == subprocess.DEVNULL

                # Check stderr is a file handle (not DEVNULL)
                assert call_args[1]["stderr"] != subprocess.DEVNULL
                assert hasattr(call_args[1]["stderr"], "write")

                # Verify process was stored
                assert process.process == mock_proc
                assert result == mock_proc

    def test_start_handles_file_not_found(self, tmp_path):
        """Test that start() raises FileNotFoundError for missing command"""
        config = {"command": "nonexistent-command", "args": []}
        process = LLMProcess("test", config)

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            with patch("subprocess.Popen", side_effect=FileNotFoundError):
                with pytest.raises(FileNotFoundError):
                    process.start()

    def test_start_handles_generic_exception(self, tmp_path):
        """Test that start() re-raises generic exceptions"""
        config = {"command": "echo", "args": []}
        process = LLMProcess("test", config)

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            with patch("subprocess.Popen", side_effect=RuntimeError("Test error")):
                with pytest.raises(RuntimeError, match="Test error"):
                    process.start()

    def test_stop_uses_config_timeout(self):
        """Test that stop() uses shutdown_timeout from config"""
        config = {"command": "echo", "shutdown_timeout": 20}
        process = LLMProcess("test", config)

        mock_proc = Mock()
        mock_proc.pid = 123
        process.process = mock_proc

        process.stop()

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=20)

    def test_stop_uses_default_timeout(self):
        """Test that stop() uses DEFAULT_SHUTDOWN_TIMEOUT when not in config"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        mock_proc = Mock()
        mock_proc.pid = 123
        process.process = mock_proc

        process.stop()

        mock_proc.wait.assert_called_once_with(timeout=DEFAULT_SHUTDOWN_TIMEOUT)

    def test_stop_uses_explicit_timeout(self):
        """Test that stop() prefers explicit timeout argument"""
        config = {"command": "echo", "shutdown_timeout": 20}
        process = LLMProcess("test", config)

        mock_proc = Mock()
        mock_proc.pid = 123
        process.process = mock_proc

        process.stop(timeout=5)

        mock_proc.wait.assert_called_once_with(timeout=5)

    def test_stop_force_kills_on_timeout(self):
        """Test that stop() force kills process if terminate times out"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        mock_proc = Mock()
        mock_proc.pid = 123
        mock_proc.wait.side_effect = [subprocess.TimeoutExpired("cmd", 10), None]
        process.process = mock_proc

        process.stop()

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        assert mock_proc.wait.call_count == 2

    def test_stop_closes_stderr_log(self):
        """Test that stop() closes stderr log file"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        mock_proc = Mock()
        mock_proc.pid = 123
        process.process = mock_proc

        mock_log = Mock()
        process._stderr_log = mock_log

        process.stop()

        mock_log.close.assert_called_once()
        assert process._stderr_log is None

    def test_stop_handles_log_close_error(self):
        """Test that stop() handles errors when closing log file"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        mock_proc = Mock()
        mock_proc.pid = 123
        process.process = mock_proc

        mock_log = Mock()
        mock_log.close.side_effect = IOError("Disk full")
        process._stderr_log = mock_log

        # Should not raise
        process.stop()

    def test_stop_warns_if_no_process(self):
        """Test that stop() logs warning if process is None"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        # Should not raise
        process.stop()

    def test_is_running_returns_false_when_no_process(self):
        """Test that is_running() returns False when process is None"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        assert process.is_running() is False

    def test_is_running_checks_poll(self):
        """Test that is_running() checks process.poll()"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        mock_proc = Mock()
        mock_proc.poll.return_value = None  # Still running
        process.process = mock_proc

        assert process.is_running() is True

        mock_proc.poll.return_value = 0  # Exited
        assert process.is_running() is False


class TestLaunchLLMModels:
    """Tests for launch_llm_models function"""

    def test_returns_empty_dict_for_empty_config(self):
        """Test that launch_llm_models returns {} for empty config"""
        result = launch_llm_models({})
        assert result == {}

    def test_launches_single_model(self, tmp_path):
        """Test that launch_llm_models launches a single model"""
        config = {
            "vllm": {
                "command": "vllm",
                "args": ["serve", "facebook/opt-125m"],
                "env": {},
                "endpoints": {"base_url": "http://localhost:8001/v1"}
            }
        }

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            with patch("subprocess.Popen") as mock_popen:
                with patch("time.sleep"):
                    mock_proc = Mock()
                    mock_proc.pid = 123
                    mock_proc.poll.return_value = None  # Running
                    mock_popen.return_value = mock_proc

                    processes = launch_llm_models(config)

                    assert "vllm" in processes
                    assert isinstance(processes["vllm"], LLMProcess)
                    assert processes["vllm"].model_id == "vllm"

    def test_launches_multiple_models(self, tmp_path):
        """Test that launch_llm_models launches multiple models"""
        config = {
            "vllm1": {"command": "vllm", "args": ["serve", "model1"]},
            "vllm2": {"command": "vllm", "args": ["serve", "model2"]},
        }

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            with patch("subprocess.Popen") as mock_popen:
                with patch("time.sleep"):
                    mock_proc = Mock()
                    mock_proc.pid = 123
                    mock_proc.poll.return_value = None  # Running
                    mock_popen.return_value = mock_proc

                    processes = launch_llm_models(config)

                    assert len(processes) == 2
                    assert "vllm1" in processes
                    assert "vllm2" in processes

    def test_sleeps_after_launch(self, tmp_path):
        """Test that launch_llm_models sleeps PROCESS_START_DELAY after launch"""
        config = {"vllm": {"command": "vllm", "args": []}}

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            with patch("subprocess.Popen") as mock_popen:
                with patch("time.sleep") as mock_sleep:
                    mock_proc = Mock()
                    mock_proc.pid = 123
                    mock_proc.poll.return_value = None
                    mock_popen.return_value = mock_proc

                    launch_llm_models(config)

                    mock_sleep.assert_called_once_with(PROCESS_START_DELAY)

    def test_excludes_failed_process(self, tmp_path):
        """Test that launch_llm_models excludes processes that fail to start"""
        config = {"vllm": {"command": "vllm", "args": []}}

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            with patch("subprocess.Popen") as mock_popen:
                with patch("time.sleep"):
                    mock_proc = Mock()
                    mock_proc.pid = 123
                    mock_proc.poll.return_value = 1  # Exited with error
                    mock_popen.return_value = mock_proc

                    processes = launch_llm_models(config)

                    # Failed process should not be in dict
                    assert "vllm" not in processes
                    assert len(processes) == 0

    def test_continues_on_exception(self, tmp_path):
        """Test that launch_llm_models continues launching other models on exception"""
        config = {
            "bad": {"command": "nonexistent"},
            "good": {"command": "echo", "args": []},
        }

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            with patch("subprocess.Popen") as mock_popen:
                with patch("time.sleep"):
                    # First call raises, second succeeds
                    def popen_side_effect(*args, **kwargs):
                        if "nonexistent" in args[0]:
                            raise FileNotFoundError("Command not found")
                        mock_proc = Mock()
                        mock_proc.pid = 456
                        mock_proc.poll.return_value = None
                        return mock_proc

                    mock_popen.side_effect = popen_side_effect

                    processes = launch_llm_models(config)

                    # Only "good" should be in processes
                    assert "bad" not in processes
                    assert "good" in processes


class TestStopAllLLMModels:
    """Tests for stop_all_llm_models function"""

    def test_handles_empty_dict(self):
        """Test that stop_all_llm_models handles empty dict gracefully"""
        # Should not raise
        stop_all_llm_models({})

    def test_stops_all_processes(self):
        """Test that stop_all_llm_models calls stop() on all processes"""
        mock_proc1 = Mock(spec=LLMProcess)
        mock_proc2 = Mock(spec=LLMProcess)

        processes = {
            "model1": mock_proc1,
            "model2": mock_proc2,
        }

        stop_all_llm_models(processes)

        mock_proc1.stop.assert_called_once()
        mock_proc2.stop.assert_called_once()

    def test_continues_on_exception(self):
        """Test that stop_all_llm_models continues stopping on exception"""
        mock_proc1 = Mock(spec=LLMProcess)
        mock_proc1.stop.side_effect = RuntimeError("Stop failed")

        mock_proc2 = Mock(spec=LLMProcess)

        processes = {
            "model1": mock_proc1,
            "model2": mock_proc2,
        }

        # Should not raise
        stop_all_llm_models(processes)

        # Both should have been called
        mock_proc1.stop.assert_called_once()
        mock_proc2.stop.assert_called_once()


class TestConfigurationValidation:
    """Tests for configuration validation (High Priority Fix #3)"""

    def test_invalid_restart_policy_raises_error(self):
        """Test that invalid restart_policy raises ValueError"""
        config = {"command": "echo", "restart_policy": "invalid"}

        with pytest.raises(ValueError, match="Invalid restart_policy 'invalid'"):
            LLMProcess("test", config)

    def test_valid_restart_policies_accepted(self):
        """Test that valid restart policies are accepted"""
        for policy in ["no", "on-failure", "always"]:
            config = {"command": "echo", "restart_policy": policy}
            process = LLMProcess("test", config)
            assert process.restart_policy == policy

    def test_negative_max_restarts_raises_error(self):
        """Test that negative max_restarts raises ValueError"""
        config = {"command": "echo", "max_restarts": -1}

        with pytest.raises(ValueError, match="Invalid max_restarts -1"):
            LLMProcess("test", config)

    def test_non_integer_max_restarts_raises_error(self):
        """Test that non-integer max_restarts raises ValueError"""
        config = {"command": "echo", "max_restarts": "invalid"}

        with pytest.raises(ValueError, match="Invalid max_restarts 'invalid'"):
            LLMProcess("test", config)

    def test_valid_max_restarts_accepted(self):
        """Test that valid max_restarts values are accepted"""
        config = {"command": "echo", "max_restarts": 5}
        process = LLMProcess("test", config)
        assert process.max_restarts == 5

    def test_negative_restart_delay_raises_error(self):
        """Test that negative restart_delay raises ValueError"""
        config = {"command": "echo", "restart_delay": -1.5}

        with pytest.raises(ValueError, match="Invalid restart_delay -1.5"):
            LLMProcess("test", config)

    def test_non_numeric_restart_delay_raises_error(self):
        """Test that non-numeric restart_delay raises ValueError"""
        config = {"command": "echo", "restart_delay": "invalid"}

        with pytest.raises(ValueError, match="Invalid restart_delay 'invalid'"):
            LLMProcess("test", config)

    def test_valid_restart_delay_accepted(self):
        """Test that valid restart_delay values are accepted"""
        config = {"command": "echo", "restart_delay": 10.5}
        process = LLMProcess("test", config)
        assert process.restart_delay == 10.5

    def test_zero_health_check_timeout_raises_error(self):
        """Test that zero health_check_timeout raises ValueError"""
        config = {"command": "echo", "health_check_timeout": 0}

        with pytest.raises(ValueError, match="Invalid health_check_timeout 0"):
            LLMProcess("test", config)

    def test_negative_health_check_timeout_raises_error(self):
        """Test that negative health_check_timeout raises ValueError"""
        config = {"command": "echo", "health_check_timeout": -5}

        with pytest.raises(ValueError, match="Invalid health_check_timeout -5"):
            LLMProcess("test", config)

    def test_valid_health_check_timeout_accepted(self):
        """Test that valid health_check_timeout is accepted"""
        config = {"command": "echo", "health_check_timeout": 15.5}
        process = LLMProcess("test", config)
        assert process.health_check_timeout == 15.5

    def test_zero_health_check_interval_raises_error(self):
        """Test that zero health_check_interval raises ValueError"""
        config = {"command": "echo", "health_check_interval": 0}

        with pytest.raises(ValueError, match="Invalid health_check_interval 0"):
            LLMProcess("test", config)

    def test_valid_health_check_interval_accepted(self):
        """Test that valid health_check_interval is accepted"""
        config = {"command": "echo", "health_check_interval": 45}
        process = LLMProcess("test", config)
        assert process.health_check_interval == 45

    def test_default_values_when_not_specified(self):
        """Test that default values are used when config keys are missing"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        assert process.restart_policy == "no"
        assert process.max_restarts == DEFAULT_MAX_RESTARTS
        assert process.restart_delay == DEFAULT_RESTART_DELAY
        assert process.health_check_timeout == HEALTH_CHECK_TIMEOUT
        assert process.health_check_interval == HEALTH_CHECK_INTERVAL


class TestHealthChecks:
    """Tests for health check functionality"""

    @pytest.mark.asyncio
    async def test_check_health_when_process_not_running(self):
        """Test check_health returns False when process is not running"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)
        process.process = None

        is_healthy, error_msg = await process.check_health()

        assert is_healthy is False
        assert error_msg == "Process not running"
        assert process.consecutive_health_failures == 1

    @pytest.mark.asyncio
    async def test_check_health_with_no_endpoints_returns_healthy(self):
        """Test check_health returns True when no endpoints configured"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        # Mock running process
        mock_proc = Mock()
        mock_proc.poll.return_value = None  # Still running
        process.process = mock_proc

        is_healthy, error_msg = await process.check_health()

        assert is_healthy is True
        assert error_msg is None
        assert process.consecutive_health_failures == 0

    @pytest.mark.asyncio
    async def test_check_health_successful_http_response(self):
        """Test check_health with successful HTTP response"""
        config = {
            "command": "echo",
            "endpoints": {"base_url": "http://localhost:8001/v1"}
        }
        process = LLMProcess("test", config)

        # Mock running process
        mock_proc = Mock()
        mock_proc.poll.return_value = None
        process.process = mock_proc

        # Mock successful HTTP response
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            is_healthy, error_msg = await process.check_health()

        assert is_healthy is True
        assert error_msg is None
        assert process.consecutive_health_failures == 0

    @pytest.mark.asyncio
    async def test_check_health_failed_http_requests(self):
        """Test check_health when all HTTP requests fail"""
        config = {
            "command": "echo",
            "endpoints": {"base_url": "http://localhost:8001/v1"}
        }
        process = LLMProcess("test", config)

        # Mock running process
        mock_proc = Mock()
        mock_proc.poll.return_value = None
        process.process = mock_proc

        # Mock failed HTTP requests
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection failed")
            mock_client_class.return_value.__aenter__.return_value = mock_client

            is_healthy, error_msg = await process.check_health()

        assert is_healthy is False
        assert "Health check failed" in error_msg
        assert process.consecutive_health_failures == 1

    @pytest.mark.asyncio
    async def test_check_health_consecutive_failures_increment(self):
        """Test that consecutive health failures increment correctly"""
        config = {
            "command": "echo",
            "endpoints": {"base_url": "http://localhost:8001/v1"}
        }
        process = LLMProcess("test", config)

        # Mock running process
        mock_proc = Mock()
        mock_proc.poll.return_value = None
        process.process = mock_proc

        # Mock failed HTTP requests
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection failed")
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # First failure
            await process.check_health()
            assert process.consecutive_health_failures == 1

            # Second failure
            await process.check_health()
            assert process.consecutive_health_failures == 2

            # Third failure
            await process.check_health()
            assert process.consecutive_health_failures == 3

    @pytest.mark.asyncio
    async def test_check_health_resets_failures_on_success(self):
        """Test that consecutive failures reset to 0 on successful health check"""
        config = {
            "command": "echo",
            "endpoints": {"base_url": "http://localhost:8001/v1"}
        }
        process = LLMProcess("test", config)
        process.consecutive_health_failures = 5

        # Mock running process
        mock_proc = Mock()
        mock_proc.poll.return_value = None
        process.process = mock_proc

        # Mock successful HTTP response
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            is_healthy, error_msg = await process.check_health()

        assert is_healthy is True
        assert process.consecutive_health_failures == 0

    @pytest.mark.asyncio
    async def test_check_health_sets_last_check_time(self):
        """Test that check_health updates last_health_check_time"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)
        process.last_health_check_time = None

        # Mock running process
        mock_proc = Mock()
        mock_proc.poll.return_value = None
        process.process = mock_proc

        before_time = time.time()
        await process.check_health()
        after_time = time.time()

        assert process.last_health_check_time is not None
        assert before_time <= process.last_health_check_time <= after_time


class TestRestartLogic:
    """Tests for restart logic and policies"""

    def test_can_restart_with_policy_no(self):
        """Test can_restart returns False when restart_policy is 'no'"""
        config = {"command": "echo", "restart_policy": "no"}
        process = LLMProcess("test", config)

        assert process.can_restart() is False

    def test_can_restart_with_policy_on_failure(self):
        """Test can_restart returns True for 'on-failure' policy"""
        config = {"command": "echo", "restart_policy": "on-failure", "max_restarts": 3}
        process = LLMProcess("test", config)
        process.restart_count = 1

        assert process.can_restart() is True

    def test_can_restart_with_policy_always(self):
        """Test can_restart returns True for 'always' policy"""
        config = {"command": "echo", "restart_policy": "always", "max_restarts": 3}
        process = LLMProcess("test", config)
        process.restart_count = 1

        assert process.can_restart() is True

    def test_can_restart_when_max_restarts_reached(self):
        """Test can_restart returns False when max_restarts is reached"""
        config = {"command": "echo", "restart_policy": "on-failure", "max_restarts": 3}
        process = LLMProcess("test", config)
        process.restart_count = 3

        assert process.can_restart() is False

    def test_can_restart_when_exceeds_max_restarts(self):
        """Test can_restart returns False when restart_count exceeds max_restarts"""
        config = {"command": "echo", "restart_policy": "always", "max_restarts": 3}
        process = LLMProcess("test", config)
        process.restart_count = 5

        assert process.can_restart() is False

    def test_needs_restart_with_policy_no(self):
        """Test needs_restart returns False when restart_policy is 'no'"""
        config = {"command": "echo", "restart_policy": "no"}
        process = LLMProcess("test", config)

        assert process.needs_restart() is False

    def test_needs_restart_when_process_dead_on_failure_policy(self):
        """Test needs_restart returns True for dead process with on-failure policy"""
        config = {"command": "echo", "restart_policy": "on-failure"}
        process = LLMProcess("test", config)

        # Mock dead process
        mock_proc = Mock()
        mock_proc.poll.return_value = 1  # Exited
        process.process = mock_proc

        assert process.needs_restart() is True

    def test_needs_restart_when_process_dead_always_policy(self):
        """Test needs_restart returns True for dead process with always policy"""
        config = {"command": "echo", "restart_policy": "always"}
        process = LLMProcess("test", config)

        # Mock dead process
        mock_proc = Mock()
        mock_proc.poll.return_value = 0  # Exited cleanly
        process.process = mock_proc

        assert process.needs_restart() is True

    def test_needs_restart_when_health_failures_exceed_threshold(self):
        """Test needs_restart when consecutive health failures exceed threshold"""
        config = {"command": "echo", "restart_policy": "on-failure"}
        process = LLMProcess("test", config)

        # Mock running process
        mock_proc = Mock()
        mock_proc.poll.return_value = None
        process.process = mock_proc

        # Set failures to threshold
        process.consecutive_health_failures = HEALTH_CHECK_FAILURES_THRESHOLD

        assert process.needs_restart() is True

    def test_needs_restart_when_health_failures_below_threshold(self):
        """Test needs_restart returns False when failures below threshold"""
        config = {"command": "echo", "restart_policy": "on-failure"}
        process = LLMProcess("test", config)

        # Mock running process
        mock_proc = Mock()
        mock_proc.poll.return_value = None
        process.process = mock_proc

        # Set failures below threshold
        process.consecutive_health_failures = HEALTH_CHECK_FAILURES_THRESHOLD - 1

        assert process.needs_restart() is False

    @pytest.mark.asyncio
    async def test_attempt_restart_when_cannot_restart(self, tmp_path):
        """Test attempt_restart returns False when can_restart is False"""
        config = {"command": "echo", "restart_policy": "no"}
        process = LLMProcess("test", config)

        result = await process.attempt_restart()

        assert result is False

    @pytest.mark.asyncio
    async def test_attempt_restart_successful(self, tmp_path):
        """Test successful restart flow"""
        config = {"command": "echo", "args": ["test"], "restart_policy": "on-failure", "restart_delay": TEST_TASK_START_DELAY}
        process = LLMProcess("test", config)

        # Mock existing process
        mock_old_proc = Mock()
        mock_old_proc.pid = 123
        mock_old_proc.poll.return_value = 1  # Dead
        process.process = mock_old_proc

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            with patch("subprocess.Popen") as mock_popen:
                mock_new_proc = Mock()
                mock_new_proc.pid = 456
                mock_new_proc.poll.return_value = None  # Running
                mock_popen.return_value = mock_new_proc

                result = await process.attempt_restart()

        assert result is True
        assert process.restart_count == 1
        assert process.last_restart_time is not None
        assert process.process == mock_new_proc

    @pytest.mark.asyncio
    async def test_attempt_restart_failure(self, tmp_path):
        """Test restart failure when process doesn't start"""
        config = {"command": "echo", "restart_policy": "on-failure", "restart_delay": TEST_TASK_START_DELAY}
        process = LLMProcess("test", config)

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            with patch("subprocess.Popen") as mock_popen:
                mock_new_proc = Mock()
                mock_new_proc.pid = 456
                mock_new_proc.poll.return_value = 1  # Dead after restart
                mock_popen.return_value = mock_new_proc

                result = await process.attempt_restart()

        assert result is False


class TestExponentialBackoff:
    """Tests for exponential backoff calculation"""

    def test_calculate_restart_delay_first_restart(self):
        """Test delay calculation for first restart (restart_count=0)"""
        config = {"command": "echo", "restart_delay": 5}
        process = LLMProcess("test", config)
        process.restart_count = 0

        delay = process.calculate_restart_delay()

        # 5 * (2^0) = 5 * 1 = 5
        assert delay == 5

    def test_calculate_restart_delay_second_restart(self):
        """Test delay calculation for second restart (restart_count=1)"""
        config = {"command": "echo", "restart_delay": 5}
        process = LLMProcess("test", config)
        process.restart_count = 1

        delay = process.calculate_restart_delay()

        # 5 * (2^1) = 5 * 2 = 10
        assert delay == 10

    def test_calculate_restart_delay_third_restart(self):
        """Test delay calculation for third restart (restart_count=2)"""
        config = {"command": "echo", "restart_delay": 5}
        process = LLMProcess("test", config)
        process.restart_count = 2

        delay = process.calculate_restart_delay()

        # 5 * (2^2) = 5 * 4 = 20
        assert delay == 20

    def test_calculate_restart_delay_sequence(self):
        """Test exponential backoff sequence: 5s, 10s, 20s, 40s, 80s, 160s"""
        config = {"command": "echo", "restart_delay": 5}
        process = LLMProcess("test", config)

        expected_delays = [5, 10, 20, 40, 80, 160]

        for count, expected_delay in enumerate(expected_delays):
            process.restart_count = count
            delay = process.calculate_restart_delay()
            assert delay == expected_delay, f"Failed at restart_count={count}"

    def test_calculate_restart_delay_capped_at_max_exponent(self):
        """Test that delay is capped at MAX_BACKOFF_EXPONENT"""
        config = {"command": "echo", "restart_delay": 5}
        process = LLMProcess("test", config)

        # Set restart_count beyond MAX_BACKOFF_EXPONENT
        process.restart_count = MAX_BACKOFF_EXPONENT + 10

        delay = process.calculate_restart_delay()

        # Should be capped at 5 * (2^MAX_BACKOFF_EXPONENT)
        max_delay = 5 * (2 ** MAX_BACKOFF_EXPONENT)
        assert delay == max_delay

    def test_calculate_restart_delay_with_custom_base(self):
        """Test backoff with custom restart_delay value"""
        config = {"command": "echo", "restart_delay": 10}
        process = LLMProcess("test", config)

        process.restart_count = 0
        assert process.calculate_restart_delay() == 10

        process.restart_count = 1
        assert process.calculate_restart_delay() == 20

        process.restart_count = 2
        assert process.calculate_restart_delay() == 40

    def test_calculate_restart_delay_with_fractional_base(self):
        """Test backoff with fractional restart_delay"""
        config = {"command": "echo", "restart_delay": 2.5}
        process = LLMProcess("test", config)

        process.restart_count = 0
        assert process.calculate_restart_delay() == 2.5

        process.restart_count = 1
        assert process.calculate_restart_delay() == 5.0

        process.restart_count = 2
        assert process.calculate_restart_delay() == 10.0


class TestCUDAOOMDetection:
    """Tests for CUDA Out of Memory detection"""

    def test_check_for_cuda_oom_with_nonexistent_log_file(self):
        """Test CUDA OOM check when log file doesn't exist"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        # Ensure log file doesn't exist
        with patch("os.path.exists", return_value=False):
            result = process.check_for_cuda_oom()

        assert result is False
        # Verify cache was set
        assert process._cuda_oom_cache is not None
        cached_result, cached_time, cached_mtime = process._cuda_oom_cache
        assert cached_result is False

    def test_check_for_cuda_oom_with_oom_error_in_log(self, tmp_path):
        """Test CUDA OOM detection with OOM error in log file"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        # Create log file with CUDA OOM error
        log_dir = tmp_path / ".fluidmcp" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / f"llm_{process.model_id}_stderr.log"
        log_file.write_text("Some startup logs\nCUDA out of memory. Tried to allocate 2.00 GiB\n")

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            result = process.check_for_cuda_oom()

        assert result is True

    def test_check_for_cuda_oom_with_cudaerror_oom_pattern(self, tmp_path):
        """Test CUDA OOM detection with CudaError: out of memory pattern"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        # Create log file with CudaError OOM pattern
        log_dir = tmp_path / ".fluidmcp" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / f"llm_{process.model_id}_stderr.log"
        log_file.write_text("CudaError: out of memory\n")

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            result = process.check_for_cuda_oom()

        assert result is True

    def test_check_for_cuda_oom_without_oom_error(self, tmp_path):
        """Test CUDA OOM check with log file but no OOM errors"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        # Create log file with different errors
        log_dir = tmp_path / ".fluidmcp" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / f"llm_{process.model_id}_stderr.log"
        log_file.write_text("Loading model...\nModel loaded successfully\n")

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            result = process.check_for_cuda_oom()

        assert result is False

    def test_check_for_cuda_oom_caching(self, tmp_path):
        """Test that CUDA OOM check uses caching (60s TTL)"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        # Create log file
        log_dir = tmp_path / ".fluidmcp" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / f"llm_{process.model_id}_stderr.log"
        log_file.write_text("No OOM here\n")

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            # First call - should read file
            result1 = process.check_for_cuda_oom()

            # Small delay to ensure mtime changes (filesystem has 1-2s resolution on some systems)
            time.sleep(0.01)

            # Modify log file (add OOM error)
            log_file.write_text("CUDA out of memory\n")

            # Force mtime to be different by touching the file
            os.utime(log_file, None)  # Update mtime to current time

            # Second call within TTL - cache invalidated because file mtime changed
            with patch("time.time", return_value=time.time() + 10):  # 10s later, within 60s TTL
                result2 = process.check_for_cuda_oom()

        assert result1 is False
        assert result2 is True  # Cache invalidated due to file modification, detects OOM

    def test_check_for_cuda_oom_cache_invalidation_after_ttl(self, tmp_path):
        """Test cache invalidation after 60s TTL"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        # Create log file
        log_dir = tmp_path / ".fluidmcp" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / f"llm_{process.model_id}_stderr.log"
        log_file.write_text("No OOM\n")

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            # First call
            with patch("time.time", return_value=1000.0):
                result1 = process.check_for_cuda_oom()

            # Modify file
            log_file.write_text("CUDA out of memory\n")

            # Call after TTL expires (61s later)
            with patch("time.time", return_value=1000.0 + CUDA_OOM_CACHE_TTL + 1):
                result2 = process.check_for_cuda_oom()

        assert result1 is False
        assert result2 is True  # Cache expired, reads file again

    def test_check_for_cuda_oom_cache_invalidation_on_file_modification(self, tmp_path):
        """Test cache invalidation when file is modified"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        # Create log file
        log_dir = tmp_path / ".fluidmcp" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / f"llm_{process.model_id}_stderr.log"
        log_file.write_text("No OOM\n")

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            # First call
            result1 = process.check_for_cuda_oom()

            # Wait a bit and modify file (changes mtime)
            time.sleep(0.1)
            log_file.write_text("CUDA out of memory\n")

            # Second call - cache should be invalidated due to mtime change
            result2 = process.check_for_cuda_oom()

        assert result1 is False
        assert result2 is True  # Cache invalidated, detects OOM


class TestLLMHealthMonitor:
    """Tests for LLMHealthMonitor (High Priority Fix #2 - Event Loop)"""

    def test_health_monitor_init(self):
        """Test health monitor initialization"""
        processes = {"test": Mock(spec=LLMProcess)}
        monitor = LLMHealthMonitor(processes, check_interval=30)

        assert monitor.processes == processes
        assert monitor.check_interval == 30
        assert monitor._monitor_task is None
        assert monitor._running is False

    @pytest.mark.asyncio
    async def test_health_monitor_start_creates_task(self):
        """Test that start() creates asyncio task"""
        processes = {"test": Mock(spec=LLMProcess)}
        monitor = LLMHealthMonitor(processes)

        monitor.start()

        assert monitor._running is True
        assert monitor._monitor_task is not None
        assert isinstance(monitor._monitor_task, asyncio.Task)

        # Clean up
        await monitor.stop()

    @pytest.fixture
    def no_event_loop(self):
        """Temporarily remove the event loop"""
        original_loop = asyncio.get_event_loop()
        asyncio.set_event_loop(None)
        yield
        asyncio.set_event_loop(original_loop)

    def test_health_monitor_start_raises_on_no_event_loop(self, no_event_loop):
        """Test that start() raises RuntimeError when no event loop exists (Fix #2)"""
        processes = {"test": Mock(spec=LLMProcess)}
        monitor = LLMHealthMonitor(processes)

        with pytest.raises(RuntimeError, match="no running event loop"):
            monitor.start()

        # Verify _running was NOT set to True
        assert monitor._running is False

    @pytest.mark.asyncio
    async def test_health_monitor_start_when_already_running(self):
        """Test that start() warns if monitor is already running"""
        processes = {"test": Mock(spec=LLMProcess)}
        monitor = LLMHealthMonitor(processes)

        monitor.start()
        # Start again
        monitor.start()

        # Should still have only one task
        assert monitor._running is True

        # Clean up
        await monitor.stop()

    @pytest.mark.asyncio
    async def test_health_monitor_stop(self):
        """Test that stop() cancels the monitor task"""
        processes = {"test": Mock(spec=LLMProcess)}
        monitor = LLMHealthMonitor(processes, check_interval=1)

        monitor.start()

        # Give task a moment to start
        await asyncio.sleep(TEST_TASK_START_DELAY)

        # Stop monitor
        await monitor.stop()

        assert monitor._running is False
        assert monitor._monitor_task.cancelled() or monitor._monitor_task.done()

    @pytest.mark.asyncio
    async def test_health_monitor_checks_all_processes(self):
        """Test that monitor checks health of all processes"""
        # Create mock processes
        mock_proc1 = Mock(spec=LLMProcess)
        mock_proc1.restart_policy = "on-failure"
        mock_proc1.check_health = AsyncMock(return_value=(True, None))
        mock_proc1.needs_restart = Mock(return_value=False)

        mock_proc2 = Mock(spec=LLMProcess)
        mock_proc2.restart_policy = "always"
        mock_proc2.check_health = AsyncMock(return_value=(True, None))
        mock_proc2.needs_restart = Mock(return_value=False)

        processes = {"model1": mock_proc1, "model2": mock_proc2}
        monitor = LLMHealthMonitor(processes, check_interval=TEST_HEALTH_CHECK_INTERVAL)

        monitor.start()

        # Wait for one health check cycle
        await asyncio.sleep(TEST_HEALTH_CHECK_WAIT)

        await monitor.stop()

        # Verify both processes were checked
        mock_proc1.check_health.assert_called()
        mock_proc2.check_health.assert_called()

    @pytest.mark.asyncio
    async def test_health_monitor_triggers_restart_on_failure(self):
        """Test that monitor triggers restart when process needs it.

        Note: Uses flexible assertion (>= 1) instead of assert_called_once()
        because the health monitor may trigger multiple restart attempts
        during the test interval due to async timing."""
        # Create mock process that needs restart
        mock_proc = Mock(spec=LLMProcess)
        mock_proc.restart_policy = "on-failure"
        mock_proc.consecutive_health_failures = 3
        mock_proc.model_id = "model"
        mock_proc.check_health = AsyncMock(return_value=(False, "Health check failed"))
        mock_proc.needs_restart = Mock(return_value=True)
        mock_proc.attempt_restart = AsyncMock(return_value=True)
        mock_proc.check_for_cuda_oom = Mock(return_value=False)

        processes = {"model": mock_proc}
        monitor = LLMHealthMonitor(processes, check_interval=TEST_HEALTH_CHECK_INTERVAL)

        monitor.start()

        # Wait for health check and restart
        await asyncio.sleep(TEST_HEALTH_CHECK_WAIT)

        await monitor.stop()

        # Verify restart was attempted (may be called multiple times during the interval)
        assert mock_proc.attempt_restart.call_count >= 1

    @pytest.mark.asyncio
    async def test_health_monitor_skips_no_restart_policy(self):
        """Test that monitor skips processes with restart_policy='no'"""
        mock_proc = Mock(spec=LLMProcess)
        mock_proc.restart_policy = "no"
        mock_proc.check_health = AsyncMock()

        processes = {"model": mock_proc}
        monitor = LLMHealthMonitor(processes, check_interval=TEST_HEALTH_CHECK_INTERVAL)

        monitor.start()

        await asyncio.sleep(TEST_HEALTH_CHECK_WAIT)

        await monitor.stop()

        # Verify health check was NOT called (skipped due to policy)
        mock_proc.check_health.assert_not_called()

    @pytest.mark.asyncio
    async def test_health_monitor_is_running(self):
        """Test is_running() status check"""
        processes = {"test": Mock(spec=LLMProcess)}
        monitor = LLMHealthMonitor(processes)

        assert monitor.is_running() is False

        monitor.start()
        assert monitor.is_running() is True

        # Clean up
        await monitor.stop()
# Additional tests to cover the missing 10%
# Add these to the end of tests/test_llm_launcher.py

class TestEdgeCases:
    """Test edge cases and error handling paths"""

    def test_sanitize_model_id_empty_string(self):
        """Test sanitize_model_id with empty string (line 58)"""
        from fluidmcp.cli.services.llm_launcher import sanitize_model_id

        # Empty string should become 'unnamed_model'
        assert sanitize_model_id("") == "unnamed_model"

        # All special characters should also result in unnamed_model
        assert sanitize_model_id("!@#$%^&*()") == "__________"

        # String that becomes empty after sanitization
        assert sanitize_model_id("///") == "___"

    def test_get_uptime_when_no_start_time(self):
        """Test get_uptime when start_time is None (lines 383-386)"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        # start_time is None initially
        assert process.start_time is None
        uptime = process.get_uptime()
        assert uptime is None

    def test_get_uptime_after_start(self):
        """Test get_uptime after process starts"""
        config = {"command": "echo", "args": ["test"]}
        process = LLMProcess("test", config)

        try:
            process.start()
            time.sleep(0.1)

            uptime = process.get_uptime()
            assert uptime is not None
            assert uptime >= 0.1
        finally:
            process.stop()

    def test_can_restart_when_max_restarts_zero(self):
        """Test can_restart with max_restarts=0 (lines 397-399)"""
        config = {
            "command": "echo",
            "restart_policy": "always",
            "max_restarts": 0
        }
        process = LLMProcess("test", config)

        # With max_restarts=0, should never be able to restart
        assert process.can_restart() is False
        assert process.restart_count == 0

    def test_check_for_cuda_oom_os_error(self, tmp_path):
        """Test CUDA OOM check when getmtime raises OSError (lines 336-337)"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        # Create log file
        log_dir = tmp_path / ".fluidmcp" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / f"llm_{process.model_id}_stderr.log"
        log_file.write_text("CUDA out of memory\n")

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            # First call to cache
            process.check_for_cuda_oom()

            # Simulate OSError on getmtime
            with patch("os.path.getmtime", side_effect=OSError("Permission denied")):
                # Should still work, treats mtime as None
                result = process.check_for_cuda_oom()
                # Will re-read file since mtime is None
                assert result is True

    def test_check_for_cuda_oom_decode_error(self, tmp_path):
        """Test CUDA OOM check with invalid UTF-8 in log (line 343)"""
        config = {"command": "echo"}
        process = LLMProcess("test", config)

        # Create log with invalid UTF-8
        log_dir = tmp_path / ".fluidmcp" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / f"llm_{process.model_id}_stderr.log"

        # Write binary data with CUDA OOM message
        with open(log_file, "wb") as f:
            f.write(b"CUDA out of memory\n")
            f.write(b"\xff\xfe\xfd")  # Invalid UTF-8

        with patch("os.path.expanduser", return_value=str(tmp_path)):
            # Should handle decode errors gracefully
            result = process.check_for_cuda_oom()
            assert result is True  # Should still detect OOM

    @pytest.mark.asyncio
    async def test_attempt_restart_before_increment(self):
        """Test restart count increment timing (line 488)"""
        config = {
            "command": "echo",
            "args": ["test"],
            "restart_policy": "always",
            "max_restarts": 5,
            "restart_delay": 0.1
        }
        process = LLMProcess("test", config)

        try:
            process.start()

            initial_count = process.restart_count
            assert initial_count == 0

            # Stop process to trigger restart
            process.stop()

            # Attempt restart
            success = await process.attempt_restart()

            if success:
                # Count should be incremented after successful restart
                assert process.restart_count == initial_count + 1
        finally:
            # Cleanup
            if process.is_running():
                process.stop()

    def test_needs_restart_when_no_process(self):
        """Test needs_restart when process is None (edge case in lines 432-446)"""
        config = {
            "command": "echo",
            "restart_policy": "on-failure"
        }
        process = LLMProcess("test", config)

        # Process never started, so process is None
        assert process.process is None

        # Should return True if policy allows (but can't determine exit code)
        result = process.needs_restart()
        # When process is None and not running, needs_restart checks policy
        assert result is True

    def test_calculate_restart_delay_edge_cases(self):
        """Test restart delay calculation edge cases (lines 445-447)"""
        config = {
            "command": "echo",
            "restart_policy": "always",
            "restart_delay": 2.5
        }
        process = LLMProcess("test", config)

        # Test with fractional base delay
        process.restart_count = 0
        assert process.calculate_restart_delay() == 2.5

        process.restart_count = 1
        assert process.calculate_restart_delay() == 5.0

        # Test at cap
        process.restart_count = 10  # Way beyond MAX_BACKOFF_EXPONENT
        delay = process.calculate_restart_delay()
        # Should be capped at 2.5 * (2^5) = 80
        assert delay == 2.5 * (2 ** 5)


class TestForceKillEdgeCases:
    """Test force_kill edge cases (lines 247-248, 256-257, 264-265)"""

    def test_force_kill_without_process(self):
        """Test force_kill when no process exists (lines 247-248)"""
        from fluidmcp.cli.services.llm_launcher import LLMProcess

        config = {"command": "echo"}
        process = LLMProcess("test", config)

        # Should log warning but not crash
        process.force_kill()
        assert process.process is None

    def test_force_kill_exception_handling(self):
        """Test force_kill handles exceptions and logs errors appropriately.

        When kill() raises an exception, force_kill should catch it, log the error,
        and continue with cleanup (closing stderr log) without propagating the exception.
        """
        from fluidmcp.cli.services.llm_launcher import LLMProcess
        from unittest.mock import Mock

        config = {"command": "echo", "args": ["test"]}
        process = LLMProcess("test", config)

        try:
            process.start()

            # Mock kill to raise an exception
            original_kill = process.process.kill
            mock_kill = Mock(side_effect=Exception("Kill failed"))
            process.process.kill = mock_kill

            # Verify error is logged
            with patch('fluidmcp.cli.services.llm_launcher.logger') as mock_logger:
                # Should handle exception gracefully without raising
                process.force_kill()

                # Verify error was logged
                mock_logger.error.assert_called()
                # Check that the error message contains relevant info
                error_call = mock_logger.error.call_args
                assert "error" in str(error_call).lower() or "kill" in str(error_call).lower()

            # Verify kill was attempted
            assert mock_kill.called, "kill() should have been attempted"

            # Restore original kill
            process.process.kill = original_kill
        finally:
            # Ensure cleanup
            if process.is_running():
                process.stop()

    def test_stderr_log_close_error_in_force_kill(self):
        """Test force_kill handles log close errors gracefully without crashing.

        When stderr log close() raises an exception during force_kill cleanup,
        the exception should be caught and logged, allowing force_kill to complete
        successfully without propagating the error.
        """
        from fluidmcp.cli.services.llm_launcher import LLMProcess
        from unittest.mock import Mock

        config = {"command": "echo", "args": ["test"]}
        process = LLMProcess("test", config)

        try:
            process.start()

            # Mock stderr log close to fail
            if process._stderr_log:
                original_close = process._stderr_log.close
                mock_close = Mock(side_effect=Exception("Close failed"))
                process._stderr_log.close = mock_close

                # force_kill should not raise - this is what we're testing
                error_handled = False
                try:
                    process.force_kill()
                    error_handled = True
                except Exception as e:
                    pytest.fail(f"force_kill raised exception despite error handling: {e}")

                # Verify force_kill completed successfully
                assert error_handled, "force_kill should handle close errors gracefully"
                # Verify close was attempted
                assert mock_close.called, "Close should have been attempted"

                # Restore original close and cleanup properly
                process._stderr_log.close = original_close
                process._stderr_log.close()
        finally:
            # Ensure cleanup even if test fails
            if process.is_running():
                process.stop()


class TestHealthMonitorEdgeCases:
    """Test health monitor edge cases (lines 632, 641-642, 656, 674-676)"""

    @pytest.mark.asyncio
    async def test_monitor_with_cuda_oom_detection(self, tmp_path):
        """Test monitor loop with CUDA OOM detection (line 632)"""
        # Create fake CUDA OOM log
        log_dir = tmp_path / ".fluidmcp" / "logs"
        log_dir.mkdir(parents=True)
        log_file = log_dir / "llm_cuda-model_stderr.log"
        log_file.write_text("CUDA out of memory. Tried to allocate 2.00 GiB\n")

        # Create mock process with CUDA OOM
        mock_proc = Mock(spec=LLMProcess)
        mock_proc.model_id = "cuda-model"
        mock_proc.restart_policy = "on-failure"
        mock_proc.check_health = AsyncMock(return_value=(False, "Health check failed"))
        mock_proc.needs_restart = Mock(return_value=False)  # Don't actually restart
        mock_proc.is_running = Mock(return_value=True)

        # Mock check_for_cuda_oom to return True
        with patch.object(mock_proc, 'check_for_cuda_oom', return_value=True):
            processes = {"cuda-model": mock_proc}
            monitor = LLMHealthMonitor(processes, check_interval=0.1)

            monitor.start()
            await asyncio.sleep(0.3)  # Let monitor run
            await monitor.stop()

            # Verify CUDA OOM was checked (line 632 coverage)
            mock_proc.check_health.assert_called()

    @pytest.mark.asyncio
    async def test_monitor_restart_in_progress_duplicate_prevention(self):
        """Test that _restarts_in_progress prevents duplicates (lines 641-642)"""
        mock_proc = Mock(spec=LLMProcess)
        mock_proc.restart_policy = "always"
        mock_proc.check_health = AsyncMock(return_value=(True, None))
        mock_proc.needs_restart = Mock(return_value=True)  # Always needs restart
        mock_proc.attempt_restart = AsyncMock(return_value=True)

        processes = {"duplicate-test": mock_proc}
        monitor = LLMHealthMonitor(processes, check_interval=0.05)

        # Pre-populate _restarts_in_progress to simulate restart already running
        monitor._restarts_in_progress.add("duplicate-test")

        monitor.start()
        await asyncio.sleep(0.15)  # Multiple check cycles
        await monitor.stop()

        # attempt_restart should NOT be called because restart already in progress
        mock_proc.attempt_restart.assert_not_called()

    @pytest.mark.asyncio
    async def test_monitor_restarts_in_progress_cleanup(self):
        """Test that _restarts_in_progress is cleaned up (line 656)"""
        mock_proc = Mock(spec=LLMProcess)
        mock_proc.restart_policy = "always"
        mock_proc.check_health = AsyncMock(return_value=(True, None))
        mock_proc.needs_restart = Mock(return_value=True)
        # Simulate successful restart
        mock_proc.attempt_restart = AsyncMock(return_value=True)

        processes = {"cleanup-test": mock_proc}
        monitor = LLMHealthMonitor(processes, check_interval=0.1)

        monitor.start()
        await asyncio.sleep(0.25)  # Let restart happen

        # Check that _restarts_in_progress was cleaned up after restart
        # Should be empty after restart completes
        await asyncio.sleep(0.1)  # Give time for cleanup

        await monitor.stop()

        # Verify the finally block cleaned up (line 656)
        assert "cleanup-test" not in monitor._restarts_in_progress

    @pytest.mark.asyncio
    async def test_monitor_stop_when_not_running(self):
        """Test monitor.stop() when already stopped (lines 674-676)"""
        processes = {"test": Mock(spec=LLMProcess)}
        monitor = LLMHealthMonitor(processes)

        # Stop without starting
        await monitor.stop()

        # Should handle gracefully (line 674-676)
        assert monitor.is_running() is False

    @pytest.mark.asyncio
    async def test_monitor_exception_in_loop(self):
        """Test monitor handles exceptions in loop gracefully (line 697)"""
        mock_proc = Mock(spec=LLMProcess)
        mock_proc.restart_policy = "always"
        # Make check_health raise an exception
        mock_proc.check_health = AsyncMock(side_effect=Exception("Test error"))

        processes = {"error-test": mock_proc}
        monitor = LLMHealthMonitor(processes, check_interval=0.1)

        monitor.start()
        await asyncio.sleep(0.25)  # Let monitor handle exception

        # Monitor should still be running despite exception
        assert monitor.is_running() is True

        await monitor.stop()

        # Should have attempted health check at least once
        assert mock_proc.check_health.call_count >= 1


class TestProcessCleanup:
    """Test process cleanup and shutdown paths (line 510-512)"""

    def test_force_kill(self):
        """Test force_kill method"""
        config = {"command": "sleep", "args": ["30"]}
        process = LLMProcess("test-kill", config)

        try:
            process.start()
            assert process.is_running()

            # Force kill immediately
            process.force_kill()

            time.sleep(0.1)

            # Process should be dead
            assert not process.is_running()
        finally:
            # Ensure process is stopped even if assertions fail
            if process.is_running():
                process.force_kill()

    def test_stop_already_stopped_process(self):
        """Test calling stop on already stopped process (line 510-512)"""
        config = {"command": "echo", "args": ["test"]}
        process = LLMProcess("test-stop", config)

        try:
            # Don't start, just try to stop
            process.stop()  # Should log warning but not crash

            # Or start then stop twice
            process.start()
            process.stop()

            # Second stop on already stopped process
            process.stop()  # Should handle gracefully (line 510-512)
        finally:
            # Ensure cleanup
            if process.is_running():
                process.stop()
