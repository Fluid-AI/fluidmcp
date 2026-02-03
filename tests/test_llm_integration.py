"""
Integration tests for the LLM launcher module.

Tests the lifecycle of LLM servers using mock processes, including startup,
graceful shutdown, process state tracking, configuration validation, environment
filtering, and basic command/log handling.

Note: These tests verify core functionality that exists in the actual implementation.
Some advanced features (such as health checks and advanced error recovery) may not
be fully tested here as they require the complete runtime environment.
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


class TestLLMProcessLifecycle:
    """Test LLM process startup and shutdown."""

    @patch('subprocess.Popen')
    @patch('os.makedirs')
    @patch('builtins.open')
    @patch('os.chmod')
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_successful_startup(self, mock_exists, mock_getsize, mock_chmod, mock_open, mock_makedirs, mock_popen, vllm_config, mock_process):
        """Test successful process startup."""
        mock_popen.return_value = mock_process
        mock_file = Mock()
        mock_open.return_value = mock_file
        mock_exists.return_value = False  # No existing log file

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
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_startup_missing_command(self, mock_exists, mock_getsize, mock_chmod, mock_open, mock_makedirs, mock_popen):
        """Test startup fails with missing command."""
        config = {"args": ["serve"]}
        llm_process = LLMProcess("test", config)
        mock_exists.return_value = False

        with pytest.raises(ValueError, match="missing 'command' in config"):
            llm_process.start()

    @patch('subprocess.Popen')
    @patch('os.makedirs')
    @patch('builtins.open')
    @patch('os.chmod')
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_graceful_shutdown(self, mock_exists, mock_getsize, mock_chmod, mock_open, mock_makedirs, mock_popen, vllm_config, mock_process):
        """Test graceful process shutdown."""
        mock_popen.return_value = mock_process
        mock_file = Mock()
        mock_open.return_value = mock_file
        mock_exists.return_value = False

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

    @patch('fluidmcp.cli.services.llm_launcher.logger')
    @patch('subprocess.Popen')
    @patch('os.makedirs')
    @patch('builtins.open')
    @patch('os.chmod')
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_command_sanitization_in_logs(self, mock_exists, mock_getsize, mock_chmod, mock_open, mock_makedirs, mock_popen, mock_logger):
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
        mock_exists.return_value = False

        llm_process = LLMProcess("test", config)
        llm_process.start()

        # Verify logger.debug was called with sanitized command
        mock_logger.debug.assert_called()
        debug_calls = [str(call) for call in mock_logger.debug.call_args_list]
        logged_output = ' '.join(debug_calls)

        # Sensitive values should be redacted
        assert "secret123" not in logged_output
        assert "abc" not in logged_output
        assert "***REDACTED***" in logged_output


class TestProcessState:
    """Test process state tracking."""

    @patch('subprocess.Popen')
    @patch('os.makedirs')
    @patch('builtins.open')
    @patch('os.chmod')
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_is_running_returns_correct_state(self, mock_exists, mock_getsize, mock_chmod, mock_open, mock_makedirs, mock_popen, vllm_config):
        """Test is_running() returns correct process state."""
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None  # Running
        mock_popen.return_value = mock_process
        mock_file = Mock()
        mock_open.return_value = mock_file
        mock_exists.return_value = False

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

    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_empty_config(self, mock_exists, mock_getsize):
        """Test empty configuration raises error."""
        llm_process = LLMProcess("test", {})
        mock_exists.return_value = False

        with pytest.raises(ValueError, match="missing 'command' in config"):
            llm_process.start()

    @patch('subprocess.Popen')
    @patch('os.makedirs')
    @patch('builtins.open')
    @patch('os.chmod')
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_unsafe_model_id_sanitization(self, mock_exists, mock_getsize, mock_chmod, mock_open, mock_makedirs, mock_popen):
        """Test that unsafe model IDs are sanitized in log paths."""
        config = {
            "command": "vllm",
            "args": ["serve", "model"],
            "endpoints": {"base_url": "http://localhost:8001/v1"}
        }

        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process
        mock_file = Mock()
        mock_open.return_value = mock_file
        mock_exists.return_value = False

        # Test with path traversal attack
        llm_process = LLMProcess("../../etc/passwd", config)
        llm_process.start()

        # Verify the log path was sanitized (no ../ sequences)
        open_call_args = mock_open.call_args[0]
        log_path = open_call_args[0]
        assert "../" not in log_path
        assert "______etc_passwd" in log_path

        # Test with spaces and special characters
        llm_process2 = LLMProcess("my model name!", config)
        llm_process2.start()

        open_call_args2 = mock_open.call_args[0]
        log_path2 = open_call_args2[0]
        assert " " not in log_path2
        assert "!" not in log_path2
        assert "my_model_name_" in log_path2

    @patch('subprocess.Popen')
    @patch('os.makedirs')
    @patch('builtins.open')
    @patch('os.chmod')
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_config_with_optional_fields(self, mock_exists, mock_getsize, mock_chmod, mock_open, mock_makedirs, mock_popen):
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
        mock_exists.return_value = False

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
    @patch('os.path.getsize')
    @patch('os.path.exists')
    def test_user_env_always_included(self, mock_exists, mock_getsize, mock_chmod, mock_open, mock_makedirs, mock_popen):
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
        mock_exists.return_value = False

        llm_process = LLMProcess("test", config)
        llm_process.start()

        # Check that user env was passed to subprocess
        popen_call = mock_popen.call_args
        env_arg = popen_call[1]['env']
        assert 'MY_SECRET' in env_arg
        assert env_arg['MY_SECRET'] == "value123"
        assert 'CUSTOM_VAR' in env_arg
        assert env_arg['CUSTOM_VAR'] == "custom"


class TestLogRotation:
    """Test log rotation functionality."""

    @patch('subprocess.Popen')
    @patch('os.makedirs')
    @patch('builtins.open')
    @patch('os.chmod')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    def test_log_rotation_triggers_when_exceeds_max_bytes(
        self, mock_getsize, mock_exists, mock_chmod, mock_open, mock_makedirs, mock_popen
    ):
        """Test that log rotation triggers when log file exceeds LOG_MAX_BYTES."""
        from fluidmcp.cli.services.llm_launcher import LOG_MAX_BYTES

        config = {
            "command": "test",
            "args": [],
            "env": {},
            "endpoints": {"base_url": "http://localhost:8001"}
        }

        # Mock process
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process

        # Mock file handle
        mock_file = Mock()
        mock_open.return_value = mock_file

        # Simulate log file exists and exceeds max size
        mock_exists.return_value = True
        mock_getsize.return_value = LOG_MAX_BYTES + 1  # Over limit

        llm_process = LLMProcess("test", config)

        # Mock the _rotate_log_files method to verify it gets called
        with patch.object(llm_process, '_rotate_log_files') as mock_rotate:
            llm_process.start()

            # Verify rotation was called with the log path
            assert mock_rotate.call_count == 1
            log_path = llm_process.get_stderr_log_path()
            mock_rotate.assert_called_once_with(log_path)

    @patch('subprocess.Popen')
    @patch('os.makedirs')
    @patch('builtins.open')
    @patch('os.chmod')
    @patch('os.path.exists')
    @patch('os.path.getsize')
    def test_log_rotation_skipped_when_under_max_bytes(
        self, mock_getsize, mock_exists, mock_chmod, mock_open, mock_makedirs, mock_popen
    ):
        """Test that log rotation is skipped when log file is under LOG_MAX_BYTES."""
        from fluidmcp.cli.services.llm_launcher import LOG_MAX_BYTES

        config = {
            "command": "test",
            "args": [],
            "env": {},
            "endpoints": {"base_url": "http://localhost:8001"}
        }

        # Mock process
        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None
        mock_popen.return_value = mock_process

        # Mock file handle
        mock_file = Mock()
        mock_open.return_value = mock_file

        # Simulate log file exists but is under max size
        mock_exists.return_value = True
        mock_getsize.return_value = LOG_MAX_BYTES - 1  # Under limit

        llm_process = LLMProcess("test", config)

        # Mock the _rotate_log_files method to verify it does NOT get called
        with patch.object(llm_process, '_rotate_log_files') as mock_rotate:
            llm_process.start()

            # Verify rotation was NOT called
            mock_rotate.assert_not_called()

    @patch('os.path.exists')
    @patch('os.remove')
    @patch('shutil.move')
    def test_log_rotation_respects_backup_count(self, mock_move, mock_remove, mock_exists):
        """Test that log rotation respects LOG_BACKUP_COUNT."""
        from fluidmcp.cli.services.llm_launcher import LOG_BACKUP_COUNT

        config = {
            "command": "test",
            "args": [],
            "env": {},
            "endpoints": {"base_url": "http://localhost:8001"}
        }

        llm_process = LLMProcess("test", config)
        log_path = "/tmp/test.log"

        # Simulate all backups exist
        def exists_side_effect(path):
            # Current log and all 5 backups exist
            if path == log_path:
                return True
            if path in [f"{log_path}.{i}" for i in range(1, LOG_BACKUP_COUNT + 1)]:
                return True
            return False

        mock_exists.side_effect = exists_side_effect

        # Call rotation
        llm_process._rotate_log_files(log_path)

        # Verify oldest backup (.5) was removed
        mock_remove.assert_called_once_with(f"{log_path}.{LOG_BACKUP_COUNT}")

        # Verify rotation chain: .4 -> .5, .3 -> .4, .2 -> .3, .1 -> .2, current -> .1
        expected_moves = [
            (f"{log_path}.4", f"{log_path}.5"),
            (f"{log_path}.3", f"{log_path}.4"),
            (f"{log_path}.2", f"{log_path}.3"),
            (f"{log_path}.1", f"{log_path}.2"),
            (log_path, f"{log_path}.1"),
        ]

        assert mock_move.call_count == 5
        actual_calls = [call[0] for call in mock_move.call_args_list]
        assert actual_calls == expected_moves
