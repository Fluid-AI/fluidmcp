"""
Integration tests for LLM launcher module.

Tests the complete lifecycle of LLM servers including startup, health checks,
error recovery, and graceful shutdown with mock processes.

Note: These tests verify core functionality that exists in the actual implementation.
Some advanced features may not be fully tested here as they require the complete
runtime environment.
"""

import pytest
from unittest.mock import Mock, patch
from fluidmcp.cli.services.llm_launcher import LLMProcess


@pytest.fixture
def mock_process():
    """Create a mock subprocess.Popen process."""
    process = Mock()
    process.pid = 12345
    process.poll.return_value = None  # Process is running
    process.returncode = None
    return process


@pytest.fixture
def vllm_config():
    """Sample vLLM configuration."""
    return {
        "command": "vllm",
        "args": ["serve", "facebook/opt-125m", "--port", "8001"],
        "env": {"CUDA_VISIBLE_DEVICES": "0"},
        "endpoints": {"base_url": "http://localhost:8001/v1"},
        "restart_policy": "on-failure",
        "max_restarts": 3,
        "restart_delay": 2
    }


@pytest.fixture
def basic_config():
    """Basic LLM configuration without restart policy."""
    return {
        "command": "python",
        "args": ["-m", "http.server", "8001"],
        "endpoints": {"base_url": "http://localhost:8001"}
    }


class TestLLMProcessLifecycle:
    """Test LLM process startup and shutdown."""

    @patch('subprocess.Popen')
    @patch('os.makedirs')
    @patch('builtins.open')
    @patch('os.chmod')
    def test_successful_startup(self, mock_chmod, mock_open, mock_makedirs, mock_popen, vllm_config, mock_process):
        """Test successful process startup."""
        mock_popen.return_value = mock_process
        mock_file = Mock()
        mock_open.return_value = mock_file

        llm_process = LLMProcess("vllm", vllm_config)
        llm_process.start()

        # Verify process was started
        assert llm_process.process == mock_process
        assert llm_process.process.pid == 12345  # Access via process.pid
        assert llm_process.is_running()

        # Verify log file was created with secure permissions
        mock_open.assert_called_once()
        mock_chmod.assert_called_once()
        chmod_args = mock_chmod.call_args[0]
        assert chmod_args[1] == 0o600  # Owner read/write only

        # Verify environment filtering was applied
        popen_call = mock_popen.call_args
        env_arg = popen_call[1]['env']
        # Should have CUDA_VISIBLE_DEVICES from config
        assert 'CUDA_VISIBLE_DEVICES' in env_arg
        assert env_arg['CUDA_VISIBLE_DEVICES'] == "0"

    @patch('subprocess.Popen')
    @patch('os.makedirs')
    @patch('builtins.open')
    @patch('os.chmod')
    def test_startup_missing_command(self, mock_chmod, mock_open, mock_makedirs, mock_popen):
        """Test startup fails with missing command."""
        config = {"args": ["serve"]}
        llm_process = LLMProcess("test", config)

        with pytest.raises(ValueError, match="missing 'command' in config"):
            llm_process.start()

    @patch('subprocess.Popen')
    @patch('os.makedirs')
    @patch('builtins.open')
    @patch('os.chmod')
    def test_graceful_shutdown(self, mock_chmod, mock_open, mock_makedirs, mock_popen, vllm_config, mock_process):
        """Test graceful process shutdown."""
        mock_popen.return_value = mock_process
        mock_file = Mock()
        mock_open.return_value = mock_file

        llm_process = LLMProcess("vllm", vllm_config)
        llm_process.start()

        # Simulate graceful termination
        def terminate_side_effect():
            mock_process.poll.return_value = 0
            mock_process.returncode = 0

        mock_process.terminate.side_effect = terminate_side_effect

        llm_process.stop(timeout=1)

        # Verify termination was called
        mock_process.terminate.assert_called_once()
        assert not llm_process.is_running()

    @patch('subprocess.Popen')
    @patch('os.makedirs')
    @patch('builtins.open')
    @patch('os.chmod')
    def test_stop_already_stopped_process(self, mock_chmod, mock_open, mock_makedirs, mock_popen, vllm_config):
        """Test stopping an already stopped process is safe."""
        llm_process = LLMProcess("vllm", vllm_config)

        # Process never started
        llm_process.stop()

        # Should not raise any errors
        assert not llm_process.is_running()

    @patch('subprocess.Popen')
    @patch('os.makedirs')
    @patch('builtins.open')
    @patch('os.chmod')
    def test_command_sanitization_in_logs(self, mock_chmod, mock_open, mock_makedirs, mock_popen):
        """Test that sensitive data in commands is sanitized in logs."""
        config = {
            "command": "vllm",
            "args": ["serve", "model", "--api-key", "secret123", "--token", "abc"],
            "endpoints": {"base_url": "http://localhost:8001/v1"}
        }

        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process
        mock_file = Mock()
        mock_open.return_value = mock_file

        llm_process = LLMProcess("test", config)
        llm_process.start()

        # Command should have been sanitized before logging
        # (This is verified by the command sanitization tests in test_llm_security.py)
        assert mock_popen.called


class TestProcessState:
    """Test process state tracking."""

    @patch('subprocess.Popen')
    @patch('os.makedirs')
    @patch('builtins.open')
    @patch('os.chmod')
    def test_is_running_returns_correct_state(self, mock_chmod, mock_open, mock_makedirs, mock_popen, vllm_config):
        """Test is_running() returns correct process state."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None  # Running
        mock_popen.return_value = mock_process
        mock_file = Mock()
        mock_open.return_value = mock_file

        llm_process = LLMProcess("vllm", vllm_config)

        # Before start
        assert not llm_process.is_running()

        # After start
        llm_process.start()
        assert llm_process.is_running()

        # After process exits
        mock_process.poll.return_value = 0
        assert not llm_process.is_running()


class TestConfigurationValidation:
    """Test configuration validation."""

    def test_empty_config(self):
        """Test empty configuration raises error."""
        llm_process = LLMProcess("test", {})

        with pytest.raises(ValueError, match="missing 'command' in config"):
            llm_process.start()

    @patch('subprocess.Popen')
    @patch('os.makedirs')
    @patch('builtins.open')
    @patch('os.chmod')
    def test_config_with_optional_fields(self, mock_chmod, mock_open, mock_makedirs, mock_popen):
        """Test configuration with all optional fields."""
        config = {
            "command": "vllm",
            "args": ["serve", "model"],
            "env": {"VAR1": "value1", "VAR2": "value2"},
            "endpoints": {"base_url": "http://localhost:8001/v1"},
            "restart_policy": "on-failure",
            "max_restarts": 5,
            "restart_delay": 10,
            "health_check_interval": 60,
            "health_check_failures": 3
        }

        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        mock_file = Mock()
        mock_open.return_value = mock_file

        llm_process = LLMProcess("test", config)
        llm_process.start()

        assert llm_process.is_running()
        assert llm_process.config["max_restarts"] == 5
        assert llm_process.config["restart_delay"] == 10


class TestEnvironmentFiltering:
    """Test environment variable filtering."""

    @patch('subprocess.Popen')
    @patch('os.makedirs')
    @patch('builtins.open')
    @patch('os.chmod')
    def test_user_env_always_included(self, mock_chmod, mock_open, mock_makedirs, mock_popen):
        """Test user-provided env vars are always included."""
        config = {
            "command": "test",
            "args": [],
            "env": {"MY_SECRET": "value123", "CUSTOM_VAR": "custom"},
            "endpoints": {"base_url": "http://localhost:8001"}
        }

        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        mock_file = Mock()
        mock_open.return_value = mock_file

        llm_process = LLMProcess("test", config)
        llm_process.start()

        # Check that user env was passed to subprocess
        popen_call = mock_popen.call_args
        env_arg = popen_call[1]['env']
        assert 'MY_SECRET' in env_arg
        assert env_arg['MY_SECRET'] == "value123"
        assert 'CUSTOM_VAR' in env_arg
        assert env_arg['CUSTOM_VAR'] == "custom"
