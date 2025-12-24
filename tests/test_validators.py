import pytest

from fluidai_mcp.services.validators import (
    validate_package_string,
    validate_port_number,
    validate_github_token,
    validate_server_config,
    validate_env_dict,
)


class TestValidatePackageString:
    def test_valid_package_strings(self):
        assert validate_package_string("Author/Package@1.0.0")
        assert validate_package_string("author-name/pkg_name@latest")

    def test_invalid_package_strings(self):
        invalid = [
            "",
            "Package@1.0.0",
            "Author/Package",
            "Author/Package@",
            "Author@1.0.0",
            "Author!/Package@1.0.0",
        ]
        for s in invalid:
            assert not validate_package_string(s)


class TestValidatePortNumber:
    def test_valid_ports(self):
        assert validate_port_number(1)
        assert validate_port_number(8080)
        assert validate_port_number(65535)

    def test_invalid_ports(self):
        assert not validate_port_number(0)
        assert not validate_port_number(70000)
        assert not validate_port_number(-1)
        assert not validate_port_number("8080")  # type: ignore


class TestValidateGithubToken:
    def test_valid_token(self):
        assert validate_github_token("ghp_123456")

    def test_invalid_token(self):
        assert not validate_github_token("")
        assert not validate_github_token("   ")
        assert not validate_github_token(None)  # type: ignore


class TestValidateServerConfig:
    def test_valid_config(self):
        config = {
            "command": "python",
            "args": ["server.py"],
        }
        errors = validate_server_config(config)
        assert errors == []

    def test_missing_fields(self):
        config = {}
        errors = validate_server_config(config)
        assert "Missing required field: command" in errors
        assert "Missing required field: args" in errors

    def test_invalid_types(self):
        config = {
            "command": 123,
            "args": "not-a-list",
        }
        errors = validate_server_config(config)
        assert "Field 'command' must be a string" in errors
        assert "Field 'args' must be a list" in errors


class TestValidateEnvDict:
    def test_valid_env(self):
        env = {
            "API_KEY": "abc123",
            "PORT": 8080,
        }
        assert validate_env_dict(env)

    def test_invalid_env(self):
        assert not validate_env_dict("not-a-dict")  # type: ignore
        assert not validate_env_dict({1: "value"})
        assert not validate_env_dict({"KEY": object()})
