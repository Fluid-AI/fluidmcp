"""
Security tests for LLM launcher module.

Tests sanitization of commands and environment variables to prevent
credential leakage in logs and subprocess environments.
"""

from fluidmcp.cli.services.llm_launcher import (
    sanitize_command_for_logging,
    filter_safe_env_vars
)


class TestCommandSanitization:
    """Test command sanitization for safe logging."""

    def test_sanitize_api_key_in_command(self):
        """Test that API keys in --flag value format are redacted."""
        command = ["vllm", "serve", "model", "--api-key", "sk-secret123"]
        result = sanitize_command_for_logging(command)
        assert "sk-secret123" not in result
        assert "***REDACTED***" in result
        assert "vllm" in result
        assert "--api-key" in result

    def test_sanitize_key_value_format(self):
        """Test that key=value format is redacted."""
        command = ["vllm", "serve", "--token=abc123", "--port=8001"]
        result = sanitize_command_for_logging(command)
        assert "abc123" not in result
        assert "--token=***REDACTED***" in result
        assert "--port=8001" in result  # Non-sensitive preserved

    def test_sanitize_multiple_sensitive_args(self):
        """Test multiple sensitive arguments are redacted."""
        command = [
            "vllm", "serve",
            "--api-key", "key1",
            "--auth-token", "token1",
            "--secret", "secret1"
        ]
        result = sanitize_command_for_logging(command)
        assert "key1" not in result
        assert "token1" not in result
        assert "secret1" not in result
        assert result.count("***REDACTED***") == 3

    def test_sanitize_preserves_safe_args(self):
        """Test that non-sensitive args are preserved."""
        command = ["vllm", "serve", "model-name", "--port", "8001", "--gpu-memory", "0.9"]
        result = sanitize_command_for_logging(command)
        assert "vllm" in result
        assert "serve" in result
        assert "model-name" in result
        assert "--port" in result
        assert "8001" in result
        assert "--gpu-memory" in result
        assert "0.9" in result
        assert "***REDACTED***" not in result

    def test_sanitize_case_insensitive(self):
        """Test that sanitization is case-insensitive."""
        command = ["app", "--API-KEY", "secret", "--Token", "value"]
        result = sanitize_command_for_logging(command)
        assert "secret" not in result
        assert "value" not in result
        assert result.count("***REDACTED***") == 2

    def test_sanitize_password_variants(self):
        """Test various password-related flags are redacted."""
        command = [
            "app",
            "--password", "pass1",
            "--auth", "auth1",
            "--credential", "cred1"
        ]
        result = sanitize_command_for_logging(command)
        assert "pass1" not in result
        assert "auth1" not in result
        assert "cred1" not in result

    def test_sanitize_empty_command(self):
        """Test sanitization of empty command."""
        assert sanitize_command_for_logging([]) == ""

    def test_sanitize_no_sensitive_data(self):
        """Test command with no sensitive data remains unchanged."""
        command = ["ls", "-la", "/tmp"]
        result = sanitize_command_for_logging(command)
        assert result == "ls -la /tmp"

    def test_sanitize_no_false_positives(self):
        """Test that segment-based matching avoids false positives."""
        # These should NOT be redacted (contain "token"/"key" as substring but not segment)
        command = [
            "vllm", "serve", "model",
            "--tokenizer=/path/to/tokenizer",  # "token" is part of "tokenizer"
            "--monkey=123",                     # "key" is part of "monkey"
            "--keyboard-layout=us",             # "key" is part of "keyboard"
            "--api-key-rotation", "daily",      # "api-key" is not the trailing pair
            "--api-key-config=/path/config",    # "api-key" is not the trailing pair
            "--port", "8001"                    # Safe value
        ]
        result = sanitize_command_for_logging(command)

        # These should be preserved (not redacted)
        assert "--tokenizer=/path/to/tokenizer" in result
        assert "--monkey=123" in result
        assert "--keyboard-layout=us" in result
        assert "--api-key-rotation" in result
        assert "daily" in result  # Value after --api-key-rotation NOT redacted
        assert "--api-key-config=/path/config" in result
        assert "8001" in result
        assert "***REDACTED***" not in result

    def test_sanitize_true_positives(self):
        """Test that segment-based matching catches true sensitive patterns."""
        command = [
            "vllm", "serve",
            "--api-key", "secret1",           # Should redact
            "--auth-token=secret2",           # Should redact
            "--access_key", "secret3",        # Should redact
            "--my-api-key", "secret4",        # Should redact (trailing pair is api-key)
            "--prod-api-key", "secret5",      # Should redact (trailing pair is api-key)
            "--admin-access-token=secret6",   # Should redact (trailing pair is access-token)
        ]
        result = sanitize_command_for_logging(command)

        # All secrets should be redacted
        assert "secret1" not in result
        assert "secret2" not in result
        assert "secret3" not in result
        assert "secret4" not in result
        assert "secret5" not in result
        assert "secret6" not in result
        assert result.count("***REDACTED***") == 6


class TestEnvVarFiltering:
    """Test environment variable filtering for subprocess."""

    def test_filter_allowlist_only(self):
        """Test that only allowlisted env vars are included from system."""
        system_env = {
            "PATH": "/usr/bin",
            "SECRET_KEY": "dangerous",
            "CUDA_VISIBLE_DEVICES": "0",
            "AWS_SECRET_KEY": "sensitive"
        }
        user_env = {}

        result = filter_safe_env_vars(system_env, user_env)

        assert "PATH" in result
        assert result["PATH"] == "/usr/bin"
        assert "CUDA_VISIBLE_DEVICES" in result
        assert "SECRET_KEY" not in result
        assert "AWS_SECRET_KEY" not in result

    def test_filter_user_env_always_included(self):
        """Test that user env vars are always included."""
        system_env = {"PATH": "/usr/bin"}
        user_env = {
            "MY_API_KEY": "user-secret",
            "CUSTOM_VAR": "value"
        }

        result = filter_safe_env_vars(system_env, user_env)

        assert "MY_API_KEY" in result  # User vars always included
        assert "CUSTOM_VAR" in result
        assert result["MY_API_KEY"] == "user-secret"

    def test_filter_user_override_allowlist(self):
        """Test that user env can override allowlist vars."""
        system_env = {"PATH": "/usr/bin"}
        user_env = {"PATH": "/custom/path"}

        result = filter_safe_env_vars(system_env, user_env)

        assert result["PATH"] == "/custom/path"

    def test_filter_user_override_case_insensitive(self):
        """Test that user env overrides system env case-insensitively (no duplicate keys)."""
        system_env = {"Path": "C:\\Windows\\System32"}  # Windows-style casing
        user_env = {"PATH": "/custom/path"}             # Unix-style casing

        result = filter_safe_env_vars(system_env, user_env)

        # Should have only ONE PATH key (user's version), not both
        assert len(result) == 1
        assert result["PATH"] == "/custom/path"
        assert "Path" not in result  # System's key should be removed

    def test_filter_empty_envs(self):
        """Test filtering with empty environments."""
        result = filter_safe_env_vars({}, {})
        assert result == {}

    def test_filter_all_allowlisted_vars(self):
        """Test that all allowlisted vars are preserved."""
        system_env = {
            "PATH": "/bin",
            "HOME": "/home/user",
            "USER": "testuser",
            "TMPDIR": "/tmp",
            "LANG": "en_US.UTF-8",
            "LC_ALL": "en_US.UTF-8",
            "CUDA_VISIBLE_DEVICES": "0,1",
            "CUDA_DEVICE_ORDER": "PCI_BUS_ID",
            "LD_LIBRARY_PATH": "/usr/local/lib",
            "PYTHONPATH": "/opt/python",
            "VIRTUAL_ENV": "/opt/venv",
            "SECRET": "should-be-filtered"
        }
        user_env = {}

        result = filter_safe_env_vars(system_env, user_env)

        # All allowlisted vars should be present
        assert "PATH" in result
        assert "HOME" in result
        assert "USER" in result
        assert "TMPDIR" in result
        assert "LANG" in result
        assert "LC_ALL" in result
        assert "CUDA_VISIBLE_DEVICES" in result
        assert "CUDA_DEVICE_ORDER" in result
        assert "LD_LIBRARY_PATH" in result
        assert "PYTHONPATH" in result
        assert "VIRTUAL_ENV" in result

        # Non-allowlisted should be filtered
        assert "SECRET" not in result

    def test_filter_preserves_values(self):
        """Test that filtering preserves original values."""
        system_env = {
            "PATH": "/usr/local/bin:/usr/bin",
            "CUDA_VISIBLE_DEVICES": "0,1,2,3"
        }
        user_env = {"API_KEY": "test-key-123"}

        result = filter_safe_env_vars(system_env, user_env)

        assert result["PATH"] == "/usr/local/bin:/usr/bin"
        assert result["CUDA_VISIBLE_DEVICES"] == "0,1,2,3"
        assert result["API_KEY"] == "test-key-123"

    def test_filter_case_insensitive_windows(self):
        """Test that filtering is case-insensitive (Windows compatibility)."""
        system_env = {
            "Path": "C:\\Windows",          # Windows uses 'Path' not 'PATH'
            "SystemRoot": "C:\\Windows",    # Windows-specific
            "TEMP": "C:\\Temp",             # Windows temp dir
            "SECRET_KEY": "sensitive"
        }
        user_env = {}

        result = filter_safe_env_vars(system_env, user_env)

        # Case-insensitive matching should work
        assert "Path" in result
        assert result["Path"] == "C:\\Windows"
        assert "SystemRoot" in result
        assert result["SystemRoot"] == "C:\\Windows"
        assert "TEMP" in result

        # Non-allowlisted should still be filtered
        assert "SECRET_KEY" not in result
