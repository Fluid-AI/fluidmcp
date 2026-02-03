"""
Minimal unit tests for environment variable validation.

Tests critical validation paths from PR #281 review feedback.
"""

import pytest
from fastapi import HTTPException
from fluidmcp.cli.api.management import validate_env_variables


class TestEnvValidation:
    """Test environment variable validation function."""

    def test_valid_env_vars(self):
        """Test that valid env vars pass validation."""
        env = {
            "API_KEY": "sk-1234567890",
            "DATABASE_URL": "postgres://localhost/db",
            "MY_VAR_123": "value"
        }
        # Should not raise
        validate_env_variables(env)

    def test_key_with_hyphen_rejected(self):
        """Test that keys with hyphens are rejected (not POSIX compliant)."""
        env = {"MY-KEY": "value"}
        with pytest.raises(HTTPException) as exc_info:
            validate_env_variables(env)
        assert "Invalid environment variable key format" in str(exc_info.value.detail)

    def test_key_starting_with_dollar_rejected(self):
        """Test MongoDB injection prevention - keys starting with $."""
        env = {"$set": "malicious"}
        with pytest.raises(HTTPException) as exc_info:
            validate_env_variables(env)
        assert "MongoDB reserved" in str(exc_info.value.detail)

    def test_key_with_dot_rejected(self):
        """Test MongoDB injection prevention - keys with dots."""
        env = {"nested.key": "value"}
        with pytest.raises(HTTPException) as exc_info:
            validate_env_variables(env)
        assert "contains dot" in str(exc_info.value.detail)

    def test_null_byte_in_value_rejected(self):
        """Test that null bytes in values are rejected."""
        env = {"KEY": "value\x00with_null"}
        with pytest.raises(HTTPException) as exc_info:
            validate_env_variables(env)
        assert "null byte" in str(exc_info.value.detail)

    def test_too_many_vars_rejected(self):
        """Test DoS prevention - too many variables."""
        env = {f"KEY_{i}": "value" for i in range(101)}
        with pytest.raises(HTTPException) as exc_info:
            validate_env_variables(env, max_vars=100)
        assert "Too many environment variables" in str(exc_info.value.detail)

    def test_key_too_long_rejected(self):
        """Test DoS prevention - key too long."""
        env = {"A" * 257: "value"}
        with pytest.raises(HTTPException) as exc_info:
            validate_env_variables(env, max_key_length=256)
        assert "key too long" in str(exc_info.value.detail)

    def test_value_too_long_rejected(self):
        """Test DoS prevention - value too long."""
        env = {"KEY": "A" * 10241}
        with pytest.raises(HTTPException) as exc_info:
            validate_env_variables(env, max_value_length=10240)
        assert "value too long" in str(exc_info.value.detail)

    def test_shell_metacharacters_allowed(self):
        """Test that shell metacharacters are allowed (shell=False context)."""
        # These should pass because we use shell=False in subprocess
        env = {
            "PATH": "/usr/bin:/bin",
            "COMMAND": "echo 'hello'",
            "PIPE_TEST": "ls | grep test",
            "REDIRECT": "output > file.txt"
        }
        # Should not raise - shell metacharacters are safe with shell=False
        validate_env_variables(env)
