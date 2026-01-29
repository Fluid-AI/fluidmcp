"""
Tests for management API security features.

Tests command injection prevention, MongoDB injection prevention,
and input validation in the management API endpoints.
"""
import pytest
from fastapi import HTTPException

from fluidmcp.cli.api.management import validate_server_config, sanitize_input


class TestCommandInjectionPrevention:
    """Tests for command injection prevention in validate_server_config."""

    def test_reject_absolute_paths(self):
        """Test that absolute paths in command field are rejected."""
        config = {
            "command": "/usr/bin/python",
            "args": []
        }
        with pytest.raises(HTTPException, match="Absolute paths not allowed"):
            validate_server_config(config)

    def test_reject_path_separators(self):
        """Test that path separators in command field are rejected."""
        config = {
            "command": "../../bin/python",
            "args": []
        }
        with pytest.raises(HTTPException, match="path separators"):
            validate_server_config(config)

    def test_command_whitelist(self):
        """Test command whitelist enforcement."""
        # Allowed command should pass
        config = {
            "command": "python",
            "args": []
        }
        validate_server_config(config)  # Should not raise

        # Disallowed command should fail
        config = {
            "command": "rm",
            "args": []
        }
        with pytest.raises(HTTPException, match="not allowed"):
            validate_server_config(config)

    def test_missing_command_field(self):
        """Test that missing command field raises error."""
        config = {"args": []}
        with pytest.raises(HTTPException, match="must include 'command' field"):
            validate_server_config(config)

    def test_args_must_be_list(self):
        """Test that args field must be a list."""
        config = {
            "command": "python",
            "args": "not a list"
        }
        with pytest.raises(HTTPException, match="'args' must be a list"):
            validate_server_config(config)

    def test_reject_dangerous_patterns_in_args(self):
        """Test rejection of dangerous shell patterns in arguments."""
        dangerous_patterns = [
            ";", "&", "|", "`", "$(", "${", "&&", "||", "\n", "\r"
        ]

        for pattern in dangerous_patterns:
            config = {
                "command": "python",
                "args": [f"test{pattern}injection"]
            }
            with pytest.raises(HTTPException, match="dangerous pattern"):
                validate_server_config(config)

    def test_reject_shell_metacharacters(self):
        """Test rejection of shell metacharacters in arguments."""
        metacharacters = ["<", ">", ">>", "<<"]

        for char in metacharacters:
            config = {
                "command": "python",
                "args": [f"test{char}file"]
            }
            with pytest.raises(HTTPException, match="shell metacharacter"):
                validate_server_config(config)

    def test_argument_length_limit(self):
        """Test that arguments exceeding max length are rejected."""
        config = {
            "command": "python",
            "args": ["a" * 1001]  # Exceeds 1000 char limit
        }
        with pytest.raises(HTTPException, match="exceeds maximum length"):
            validate_server_config(config)

    def test_args_must_be_strings(self):
        """Test that all arguments must be strings."""
        config = {
            "command": "python",
            "args": [123, "valid"]  # Non-string argument
        }
        with pytest.raises(HTTPException, match="must be strings"):
            validate_server_config(config)

    def test_flag_format_validation(self):
        """Test validation of flag argument formats."""
        # Valid flags should pass
        valid_configs = [
            {"command": "python", "args": ["-m"]},
            {"command": "python", "args": ["--module"]},
            {"command": "python", "args": ["--config=value"]},
        ]
        for config in valid_configs:
            validate_server_config(config)  # Should not raise

        # Invalid flag formats should fail
        invalid_flags = [
            "--invalid flag",  # Space in flag
            "-invalid",  # Too long for single dash
            "--",  # Empty flag
        ]
        for flag in invalid_flags:
            config = {"command": "python", "args": [flag]}
            with pytest.raises(HTTPException, match="Invalid flag format"):
                validate_server_config(config)

    def test_valid_arguments_accepted(self):
        """Test that valid arguments are accepted."""
        config = {
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-filesystem",
                "/tmp",
                "--verbose"
            ]
        }
        validate_server_config(config)  # Should not raise


class TestEnvironmentVariableValidation:
    """Tests for environment variable validation."""

    def test_env_must_be_dict(self):
        """Test that env field must be a dictionary."""
        config = {
            "command": "python",
            "env": "not a dict"
        }
        with pytest.raises(HTTPException, match="'env' must be a dictionary"):
            validate_server_config(config)

    def test_env_keys_and_values_must_be_strings(self):
        """Test that env keys and values must be strings."""
        config = {
            "command": "python",
            "env": {
                "VALID_KEY": 123  # Non-string value
            }
        }
        with pytest.raises(HTTPException, match="must be strings"):
            validate_server_config(config)

    def test_env_var_name_validation(self):
        """Test environment variable name validation."""
        # Invalid names (lowercase, special chars)
        invalid_names = [
            "api_key",  # Lowercase
            "123KEY",  # Starts with number
            "API-KEY",  # Hyphen not allowed
            "API KEY",  # Space not allowed
        ]

        for name in invalid_names:
            config = {
                "command": "python",
                "env": {name: "value"}
            }
            with pytest.raises(HTTPException, match="Invalid environment variable name"):
                validate_server_config(config)

    def test_env_var_value_length_limit(self):
        """Test environment variable value length limit."""
        config = {
            "command": "python",
            "env": {
                "TEST_VAR": "a" * 10001  # Exceeds 10,000 char limit
            }
        }
        with pytest.raises(HTTPException, match="exceeds maximum length"):
            validate_server_config(config)

    def test_env_var_dangerous_patterns(self):
        """Test rejection of dangerous patterns in env values."""
        dangerous_patterns = [
            ";", "&", "|", "`", "$(", "${", "&&", "||", "\n", "\r"
        ]

        for pattern in dangerous_patterns:
            config = {
                "command": "python",
                "env": {
                    "TEST_VAR": f"value{pattern}injection"
                }
            }
            with pytest.raises(HTTPException, match="dangerous pattern"):
                validate_server_config(config)

    def test_valid_env_vars_accepted(self):
        """Test that valid environment variables are accepted."""
        config = {
            "command": "python",
            "env": {
                "API_KEY": "sk-1234567890",
                "DATABASE_URL": "postgresql://localhost:5432/db",
                "DEBUG_MODE": "true",
                "MAX_WORKERS": "10"
            }
        }
        validate_server_config(config)  # Should not raise


class TestMongoDBInjectionPrevention:
    """Tests for MongoDB injection prevention via input sanitization."""

    def test_sanitize_string_with_operator(self):
        """Test sanitization of strings with MongoDB operators."""
        input_str = "$where: function() { return true; }"
        result = sanitize_input(input_str)
        assert not result.startswith("$")
        assert "{" not in result
        assert "}" not in result

    def test_sanitize_string_with_braces(self):
        """Test sanitization removes braces."""
        input_str = "test{injection}attempt"
        result = sanitize_input(input_str)
        assert "{" not in result
        assert "}" not in result

    def test_sanitize_nested_dict(self):
        """Test recursive sanitization of nested dictionaries."""
        input_dict = {
            "name": "$admin",
            "config": {
                "command": "${injection}",
                "nested": {
                    "deep": "$operator"
                }
            }
        }
        result = sanitize_input(input_dict)

        assert not result["name"].startswith("$")
        assert not result["config"]["command"].startswith("$")
        assert not result["config"]["nested"]["deep"].startswith("$")
        assert "{" not in result["config"]["command"]
        assert "}" not in result["config"]["command"]

    def test_sanitize_list(self):
        """Test recursive sanitization of lists."""
        input_list = ["$item1", "normal", "${item2}", ["$nested"]]
        result = sanitize_input(input_list)

        assert not result[0].startswith("$")
        assert result[1] == "normal"
        assert not result[2].startswith("$")
        assert not result[3][0].startswith("$")

    def test_sanitize_mixed_structures(self):
        """Test sanitization of complex mixed structures."""
        input_data = {
            "servers": [
                {
                    "name": "$admin",
                    "args": ["${value}", "normal"]
                }
            ],
            "config": {
                "enabled": True,
                "value": "$test"
            }
        }
        result = sanitize_input(input_data)

        assert not result["servers"][0]["name"].startswith("$")
        assert not result["servers"][0]["args"][0].startswith("$")
        assert result["servers"][0]["args"][1] == "normal"
        assert result["config"]["enabled"] is True
        assert not result["config"]["value"].startswith("$")

    def test_sanitize_preserves_valid_data(self):
        """Test that sanitization preserves valid data."""
        input_data = {
            "id": "test-server",
            "name": "Test Server",
            "description": "A normal description",
            "enabled": True,
            "port": 8090
        }
        result = sanitize_input(input_data)

        assert result == input_data  # Should be unchanged

    def test_sanitize_empty_structures(self):
        """Test sanitization of empty structures."""
        assert sanitize_input({}) == {}
        assert sanitize_input([]) == []
        assert sanitize_input("") == ""

    def test_sanitize_non_string_types(self):
        """Test that non-string types are preserved."""
        assert sanitize_input(123) == 123
        assert sanitize_input(True) is True
        assert sanitize_input(None) is None
        assert sanitize_input(3.14) == 3.14


class TestCompleteValidationFlow:
    """Integration tests for complete validation flow."""

    def test_valid_server_config_passes(self):
        """Test that a completely valid config passes all validations."""
        config = {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "env": {
                "NODE_ENV": "production",
                "DEBUG": "false"
            }
        }
        validate_server_config(config)  # Should not raise

    def test_sanitize_then_validate_workflow(self):
        """Test the workflow of sanitizing then validating."""
        # Config with injection attempts
        config = {
            "command": "python",
            "args": ["valid-arg"],
            "env": {
                "API_KEY": "value"  # Valid after being uppercase
            }
        }

        # Sanitize
        sanitized = sanitize_input(config)

        # Validate (should pass after sanitization)
        validate_server_config(sanitized)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
