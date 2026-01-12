"""
Tests for fluidai_mcp.services.validators module.

This test suite validates all validation functions to ensure they correctly
identify valid and invalid inputs across various edge cases.
"""

import pytest
from fluidai_mcp.services.validators import (
    validate_package_string,
    validate_port_number,
    validate_github_token,
    validate_server_config,
    validate_env_dict,
    validate_mcpservers_config,
    is_valid_package_version,
)


class TestValidatePackageString:
    """Test validate_package_string function."""

    def test_valid_basic_format(self):
        """Test valid basic package strings."""
        assert validate_package_string("Author/Package@1.0.0") is True
        assert validate_package_string("Anthropic/filesystem@1.0.0") is True
        assert validate_package_string("ModelContext/memory@2.5.1") is True

    def test_valid_with_v_prefix(self):
        """Test valid package strings with 'v' prefix in version."""
        assert validate_package_string("Author/Package@v1.0.0") is True
        assert validate_package_string("Anthropic/filesystem@v2.0.0") is True

    def test_valid_with_hyphens(self):
        """Test valid package strings with hyphens in names."""
        assert validate_package_string("Author-Name/Package-Name@1.0.0") is True
        assert validate_package_string("Multi-Word/Multi-Word-Package@1.0.0") is True

    def test_valid_with_underscores(self):
        """Test valid package strings with underscores in names."""
        assert validate_package_string("Author_Name/Package_Name@1.0.0") is True
        assert validate_package_string("Test_Author/test_package@1.0.0") is True

    def test_valid_prerelease_versions(self):
        """Test valid package strings with prerelease versions."""
        assert validate_package_string("Author/Package@1.0.0-alpha") is True
        assert validate_package_string("Author/Package@1.0.0-beta.1") is True
        assert validate_package_string("Author/Package@2.0.0-rc.1") is True

    def test_valid_latest_version(self):
        """Test valid package string with 'latest' version."""
        assert validate_package_string("Author/Package@latest") is True

    def test_invalid_missing_separator(self):
        """Test invalid strings missing '/' or '@' separator."""
        assert validate_package_string("AuthorPackage@1.0.0") is False
        assert validate_package_string("Author/Package1.0.0") is False
        assert validate_package_string("AuthorPackage") is False

    def test_invalid_empty_parts(self):
        """Test invalid strings with empty author, package, or version."""
        assert validate_package_string("/Package@1.0.0") is False
        assert validate_package_string("Author/@1.0.0") is False
        assert validate_package_string("Author/Package@") is False

    def test_invalid_multiple_separators(self):
        """Test invalid strings with multiple '/' or '@' characters."""
        assert validate_package_string("Author/Sub/Package@1.0.0") is False
        assert validate_package_string("Author/Package@1.0.0@extra") is False

    def test_invalid_special_characters(self):
        """Test invalid strings with disallowed special characters."""
        assert validate_package_string("Author!/Package@1.0.0") is False
        assert validate_package_string("Author/Package$@1.0.0") is False
        assert validate_package_string("Author/Package@1.0.0#") is False

    def test_invalid_empty_or_none(self):
        """Test invalid empty or None inputs."""
        assert validate_package_string("") is False
        assert validate_package_string(None) is False

    def test_invalid_non_string_types(self):
        """Test invalid non-string types."""
        assert validate_package_string(123) is False
        assert validate_package_string(["Author/Package@1.0.0"]) is False
        assert validate_package_string({"package": "Author/Package@1.0.0"}) is False


class TestValidatePortNumber:
    """Test validate_port_number function."""

    def test_valid_well_known_ports(self):
        """Test valid well-known ports (1-1023)."""
        assert validate_port_number(80) is True
        assert validate_port_number(443) is True
        assert validate_port_number(22) is True
        assert validate_port_number(1023) is True

    def test_valid_registered_ports(self):
        """Test valid registered ports (1024-49151)."""
        assert validate_port_number(1024) is True
        assert validate_port_number(8080) is True
        assert validate_port_number(8099) is True
        assert validate_port_number(49151) is True

    def test_valid_dynamic_ports(self):
        """Test valid dynamic/private ports (49152-65535)."""
        assert validate_port_number(49152) is True
        assert validate_port_number(60000) is True
        assert validate_port_number(65535) is True

    def test_invalid_zero(self):
        """Test invalid port 0."""
        assert validate_port_number(0) is False

    def test_invalid_negative(self):
        """Test invalid negative port numbers."""
        assert validate_port_number(-1) is False
        assert validate_port_number(-100) is False

    def test_invalid_too_large(self):
        """Test invalid port numbers above 65535."""
        assert validate_port_number(65536) is False
        assert validate_port_number(70000) is False
        assert validate_port_number(100000) is False

    def test_invalid_non_integer_types(self):
        """Test invalid non-integer types."""
        assert validate_port_number("8080") is False
        assert validate_port_number(8080.5) is False
        assert validate_port_number(None) is False
        assert validate_port_number([8080]) is False


class TestValidateGithubToken:
    """Test validate_github_token function."""

    def test_valid_classic_token(self):
        """Test valid classic personal access token (ghp_...)."""
        # Classic tokens: ghp_ + 36 alphanumeric chars = 40 total
        valid_token = "ghp_" + "A" * 36
        assert validate_github_token(valid_token) is True

    def test_valid_fine_grained_token(self):
        """Test valid fine-grained personal access token (github_pat_...)."""
        # Fine-grained tokens: github_pat_ + 71 chars = 82 total
        valid_token = "github_pat_" + "A" * 71
        assert validate_github_token(valid_token) is True

    def test_valid_oauth_token(self):
        """Test valid OAuth access token (gho_...)."""
        # OAuth tokens: gho_ + 32 alphanumeric chars = 36 total
        valid_token = "gho_" + "B" * 32
        assert validate_github_token(valid_token) is True

    def test_valid_installation_token(self):
        """Test valid installation access token (ghs_...)."""
        # Installation tokens: ghs_ + 32 alphanumeric chars = 36 total
        valid_token = "ghs_" + "C" * 32
        assert validate_github_token(valid_token) is True

    def test_valid_app_token(self):
        """Test valid GitHub App token (ghu_...)."""
        # App tokens: ghu_ + 32 alphanumeric chars = 36 total
        valid_token = "ghu_" + "D" * 32
        assert validate_github_token(valid_token) is True

    def test_valid_refresh_token(self):
        """Test valid refresh token (ghr_...)."""
        # Refresh tokens: ghr_ + 72 alphanumeric chars = 76 total
        valid_token = "ghr_" + "E" * 72
        assert validate_github_token(valid_token) is True

    def test_invalid_wrong_length_classic(self):
        """Test invalid classic token with wrong length."""
        assert validate_github_token("ghp_" + "A" * 35) is False  # Too short
        assert validate_github_token("ghp_" + "A" * 37) is False  # Too long

    def test_invalid_wrong_length_fine_grained(self):
        """Test invalid fine-grained token with wrong length."""
        assert validate_github_token("github_pat_" + "A" * 70) is False  # Too short
        assert validate_github_token("github_pat_" + "A" * 72) is False  # Too long

    def test_invalid_no_prefix(self):
        """Test invalid tokens without recognized prefix."""
        assert validate_github_token("A" * 40) is False
        assert validate_github_token("token_" + "A" * 34) is False

    def test_invalid_special_characters(self):
        """Test invalid tokens with special characters."""
        assert validate_github_token("ghp_" + "A" * 35 + "!") is False
        assert validate_github_token("ghp_" + "A" * 35 + " ") is False

    def test_invalid_empty_or_none(self):
        """Test invalid empty or None inputs."""
        assert validate_github_token("") is False
        assert validate_github_token(None) is False
        assert validate_github_token("   ") is False

    def test_invalid_non_string_types(self):
        """Test invalid non-string types."""
        assert validate_github_token(123) is False
        assert validate_github_token(["token"]) is False


class TestValidateServerConfig:
    """Test validate_server_config function."""

    def test_valid_minimal_config(self):
        """Test valid minimal server configuration."""
        config = {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem"]
        }
        errors = validate_server_config(config)
        assert errors == []

    def test_valid_with_env(self):
        """Test valid server configuration with environment variables."""
        config = {
            "command": "python",
            "args": ["server.py"],
            "env": {
                "API_KEY": "secret",
                "PORT": "8080"
            }
        }
        errors = validate_server_config(config)
        assert errors == []

    def test_valid_with_structured_env(self):
        """Test valid server configuration with structured env variables."""
        config = {
            "command": "node",
            "args": ["index.js"],
            "env": {
                "API_KEY": {
                    "value": "secret",
                    "description": "API key for authentication"
                }
            }
        }
        errors = validate_server_config(config)
        assert errors == []

    def test_invalid_not_dict(self):
        """Test invalid config that is not a dictionary."""
        errors = validate_server_config("not a dict")
        assert len(errors) == 1
        assert "must be a dictionary" in errors[0]

    def test_invalid_missing_command(self):
        """Test invalid config missing 'command' field."""
        config = {"args": ["-y", "package"]}
        errors = validate_server_config(config)
        assert any("Missing required field: command" in e for e in errors)

    def test_invalid_missing_args(self):
        """Test invalid config missing 'args' field."""
        config = {"command": "npx"}
        errors = validate_server_config(config)
        assert any("Missing required field: args" in e for e in errors)

    def test_invalid_command_not_string(self):
        """Test invalid config where 'command' is not a string."""
        config = {"command": 123, "args": []}
        errors = validate_server_config(config)
        assert any("'command' must be a string" in e for e in errors)

    def test_invalid_command_empty(self):
        """Test invalid config where 'command' is empty string."""
        config = {"command": "  ", "args": []}
        errors = validate_server_config(config)
        assert any("'command' cannot be empty" in e for e in errors)

    def test_invalid_args_not_list(self):
        """Test invalid config where 'args' is not a list."""
        config = {"command": "npx", "args": "not a list"}
        errors = validate_server_config(config)
        assert any("'args' must be a list" in e for e in errors)

    def test_invalid_args_contain_non_strings(self):
        """Test invalid config where 'args' contains non-string elements."""
        config = {"command": "npx", "args": ["-y", 123, "package"]}
        errors = validate_server_config(config)
        assert any("Argument at index 1" in e for e in errors)

    def test_invalid_env_not_dict(self):
        """Test invalid config where 'env' is not a dictionary."""
        config = {"command": "npx", "args": [], "env": "not a dict"}
        errors = validate_server_config(config)
        assert any("'env' must be a dictionary" in e for e in errors)

    def test_multiple_errors(self):
        """Test config with multiple validation errors."""
        config = {"command": 123}  # Missing args, command wrong type
        errors = validate_server_config(config)
        assert len(errors) >= 2


class TestValidateEnvDict:
    """Test validate_env_dict function."""

    def test_valid_simple_format(self):
        """Test valid simple environment variable format."""
        env = {
            "API_KEY": "secret123",
            "PORT": "8080",
            "DEBUG": "true"
        }
        assert validate_env_dict(env) is True

    def test_valid_structured_format(self):
        """Test valid structured environment variable format."""
        env = {
            "API_KEY": {
                "value": "secret123",
                "description": "API key for authentication"
            },
            "PORT": {
                "value": "8080",
                "description": "Server port"
            }
        }
        assert validate_env_dict(env) is True

    def test_valid_mixed_format(self):
        """Test valid mixed simple and structured format."""
        env = {
            "API_KEY": "secret123",
            "PORT": {
                "value": "8080",
                "description": "Server port"
            }
        }
        assert validate_env_dict(env) is True

    def test_valid_lowercase_keys(self):
        """Test valid environment variables with lowercase keys."""
        env = {
            "api_key": "secret",
            "database_url": "postgres://localhost"
        }
        assert validate_env_dict(env) is True

    def test_valid_underscore_prefix(self):
        """Test valid environment variables starting with underscore."""
        env = {
            "_INTERNAL_KEY": "value",
            "_DEBUG": "true"
        }
        assert validate_env_dict(env) is True

    def test_invalid_not_dict(self):
        """Test invalid input that is not a dictionary."""
        assert validate_env_dict("not a dict") is False
        assert validate_env_dict([]) is False
        assert validate_env_dict(None) is False

    def test_invalid_key_starts_with_number(self):
        """Test invalid key starting with a number."""
        env = {"123_KEY": "value"}
        assert validate_env_dict(env) is False

    def test_invalid_key_with_special_chars(self):
        """Test invalid key with special characters."""
        env = {"API-KEY": "value"}  # Hyphens not allowed
        assert validate_env_dict(env) is False

        env = {"API.KEY": "value"}  # Dots not allowed
        assert validate_env_dict(env) is False

    def test_invalid_value_not_string(self):
        """Test invalid value that is not a string."""
        env = {"API_KEY": 123}
        assert validate_env_dict(env) is False

        env = {"PORT": 8080}
        assert validate_env_dict(env) is False

    def test_invalid_structured_missing_value(self):
        """Test invalid structured format missing 'value' key."""
        env = {
            "API_KEY": {
                "description": "API key"
            }
        }
        assert validate_env_dict(env) is False

    def test_invalid_structured_value_not_string(self):
        """Test invalid structured format with non-string value."""
        env = {
            "API_KEY": {
                "value": 123
            }
        }
        assert validate_env_dict(env) is False

    def test_invalid_structured_description_not_string(self):
        """Test invalid structured format with non-string description."""
        env = {
            "API_KEY": {
                "value": "secret",
                "description": 123
            }
        }
        assert validate_env_dict(env) is False

    def test_empty_dict(self):
        """Test empty dictionary (valid)."""
        assert validate_env_dict({}) is True


class TestValidateMcpserversConfig:
    """Test validate_mcpservers_config function."""

    def test_valid_single_server(self):
        """Test valid configuration with single server."""
        config = {
            "mcpServers": {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem"]
                }
            }
        }
        errors = validate_mcpservers_config(config)
        assert errors == []

    def test_valid_multiple_servers(self):
        """Test valid configuration with multiple servers."""
        config = {
            "mcpServers": {
                "filesystem": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem"]
                },
                "memory": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-memory"]
                }
            }
        }
        errors = validate_mcpservers_config(config)
        assert errors == []

    def test_valid_with_env(self):
        """Test valid configuration with environment variables."""
        config = {
            "mcpServers": {
                "github": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "env": {
                        "GITHUB_TOKEN": "ghp_token123"
                    }
                }
            }
        }
        errors = validate_mcpservers_config(config)
        assert errors == []

    def test_invalid_not_dict(self):
        """Test invalid config that is not a dictionary."""
        errors = validate_mcpservers_config("not a dict")
        assert len(errors) == 1
        assert "must be a dictionary" in errors[0]

    def test_invalid_missing_mcpservers(self):
        """Test invalid config missing 'mcpServers' key."""
        config = {"other": {}}
        errors = validate_mcpservers_config(config)
        assert len(errors) == 1
        assert "Missing required field: mcpServers" in errors[0]

    def test_invalid_mcpservers_not_dict(self):
        """Test invalid config where 'mcpServers' is not a dictionary."""
        config = {"mcpServers": "not a dict"}
        errors = validate_mcpservers_config(config)
        assert len(errors) == 1
        assert "'mcpServers' must be a dictionary" in errors[0]

    def test_invalid_mcpservers_empty(self):
        """Test invalid config with empty 'mcpServers'."""
        config = {"mcpServers": {}}
        errors = validate_mcpservers_config(config)
        assert len(errors) == 1
        assert "'mcpServers' cannot be empty" in errors[0]

    def test_invalid_server_name(self):
        """Test invalid empty server name."""
        config = {
            "mcpServers": {
                "": {
                    "command": "npx",
                    "args": []
                }
            }
        }
        errors = validate_mcpservers_config(config)
        assert any("Invalid server name" in e for e in errors)

    def test_invalid_server_config(self):
        """Test invalid server configuration."""
        config = {
            "mcpServers": {
                "filesystem": {
                    "command": "npx"
                    # Missing 'args'
                }
            }
        }
        errors = validate_mcpservers_config(config)
        assert len(errors) > 0
        assert any("filesystem" in e and "args" in e for e in errors)

    def test_multiple_server_errors(self):
        """Test configuration with multiple servers having errors."""
        config = {
            "mcpServers": {
                "filesystem": {
                    "command": "npx"
                    # Missing 'args'
                },
                "memory": {
                    "args": []
                    # Missing 'command'
                }
            }
        }
        errors = validate_mcpservers_config(config)
        assert len(errors) >= 2
        assert any("filesystem" in e for e in errors)
        assert any("memory" in e for e in errors)


class TestIsValidPackageVersion:
    """Test is_valid_package_version function."""

    def test_valid_basic_semver(self):
        """Test valid basic semantic versions."""
        assert is_valid_package_version("1.0.0") is True
        assert is_valid_package_version("2.5.1") is True
        assert is_valid_package_version("0.0.1") is True
        assert is_valid_package_version("10.20.30") is True

    def test_valid_with_v_prefix(self):
        """Test valid versions with 'v' prefix."""
        assert is_valid_package_version("v1.0.0") is True
        assert is_valid_package_version("v2.5.1") is True

    def test_valid_prerelease(self):
        """Test valid prerelease versions."""
        assert is_valid_package_version("1.0.0-alpha") is True
        assert is_valid_package_version("1.0.0-beta.1") is True
        assert is_valid_package_version("2.0.0-rc.1") is True
        assert is_valid_package_version("1.0.0-alpha.beta") is True

    def test_valid_latest(self):
        """Test valid 'latest' version."""
        assert is_valid_package_version("latest") is True

    def test_invalid_missing_parts(self):
        """Test invalid versions missing major/minor/patch."""
        assert is_valid_package_version("1.0") is False
        assert is_valid_package_version("1") is False
        assert is_valid_package_version("v1.0") is False

    def test_invalid_non_numeric(self):
        """Test invalid versions with non-numeric parts."""
        assert is_valid_package_version("x.y.z") is False
        assert is_valid_package_version("1.x.0") is False

    def test_invalid_special_characters(self):
        """Test invalid versions with disallowed special characters."""
        assert is_valid_package_version("1.0.0!") is False
        assert is_valid_package_version("1.0.0#beta") is False

    def test_invalid_empty_or_none(self):
        """Test invalid empty or None inputs."""
        assert is_valid_package_version("") is False
        assert is_valid_package_version(None) is False

    def test_invalid_non_string_types(self):
        """Test invalid non-string types."""
        assert is_valid_package_version(1.0) is False
        assert is_valid_package_version(["1.0.0"]) is False


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_package_string_boundary_lengths(self):
        """Test package strings with very long names."""
        long_name = "A" * 100
        assert validate_package_string(f"{long_name}/{long_name}@1.0.0") is True

    def test_port_number_boundaries(self):
        """Test port numbers at exact boundaries."""
        assert validate_port_number(1) is True  # Minimum valid
        assert validate_port_number(65535) is True  # Maximum valid
        assert validate_port_number(0) is False  # Below minimum
        assert validate_port_number(65536) is False  # Above maximum

    def test_env_dict_empty_values(self):
        """Test environment dict with empty string values (valid)."""
        env = {"API_KEY": ""}
        assert validate_env_dict(env) is True

    def test_server_config_empty_args(self):
        """Test server config with empty args list (valid)."""
        config = {"command": "python", "args": []}
        errors = validate_server_config(config)
        assert errors == []

    def test_unicode_in_strings(self):
        """Test handling of unicode characters."""
        # Unicode in package strings should be rejected
        assert validate_package_string("Authör/Package@1.0.0") is False

        # Unicode in env values should be accepted
        env = {"MESSAGE": "Hello 世界"}
        assert validate_env_dict(env) is True
