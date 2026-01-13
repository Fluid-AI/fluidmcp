"""Unit tests for llm_launcher.py"""

import os
import subprocess
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, mock_open

import pytest

from fluidmcp.cli.services.llm_launcher import (
    LLMProcess,
    launch_llm_models,
    stop_all_llm_models,
    DEFAULT_SHUTDOWN_TIMEOUT,
    PROCESS_START_DELAY,
)


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
