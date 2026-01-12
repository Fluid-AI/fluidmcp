"""
Reusable validation functions for FluidMCP.

This module provides validation utilities for:
- Package strings (Author/Package@version format)
- Port numbers (valid TCP port range)
- GitHub tokens (format and basic structure)
- Server configurations (MCP server config structure)
- Environment dictionaries (env variable format)
- MCP servers configurations (full mcpServers config structure)
- Package versions (semantic version string format)
"""

import re
from typing import Dict, List, Any


# Compiled regex patterns for performance
PACKAGE_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+@[a-zA-Z0-9._-]+$')
ENV_VAR_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
VERSION_PATTERN = re.compile(r'^\d+\.\d+\.\d+(-[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*)?$')


def validate_package_string(s: str) -> bool:
    """
    Validate package string format: Author/Package@version

    Valid formats:
    - Author/Package@1.0.0
    - Author/Package@v1.0.0
    - Author/Package@latest
    - Author-Name/Package-Name@1.0.0-beta

    Args:
        s: Package string to validate

    Returns:
        True if valid format, False otherwise

    Examples:
        >>> validate_package_string("Anthropic/filesystem@1.0.0")
        True
        >>> validate_package_string("invalid")
        False
        >>> validate_package_string("Author/Package")
        False
    """
    if not s or not isinstance(s, str):
        return False

    # Use compiled pattern for performance
    if not PACKAGE_PATTERN.match(s):
        return False

    # Additional validation: ensure we have exactly one '/' and one '@'
    if s.count('/') != 1 or s.count('@') != 1:
        return False

    # Split and extract parts
    parts = s.split('/')
    author = parts[0]
    package_version = parts[1]

    package, version = package_version.split('@', 1)

    # Check all parts are non-empty
    if not author or not package or not version:
        return False

    return True


def validate_port_number(port: int) -> bool:
    """
    Validate TCP port number is in valid range.

    Valid port range: 1-65535
    Well-known ports: 1-1023 (may require privileges)
    Registered ports: 1024-49151
    Dynamic/private ports: 49152-65535

    Args:
        port: Port number to validate

    Returns:
        True if valid port number, False otherwise

    Examples:
        >>> validate_port_number(8080)
        True
        >>> validate_port_number(0)
        False
        >>> validate_port_number(70000)
        False
    """
    # Reject bool types (bool is a subclass of int in Python)
    if isinstance(port, bool) or not isinstance(port, int):
        return False

    # Valid TCP port range: 1-65535
    return 1 <= port <= 65535


def validate_github_token(token: str) -> bool:
    """
    Validate GitHub personal access and related token formats.

    GitHub tokens have specific formats:
    - Classic tokens: ghp_... (40 chars total; 'ghp_' + 36 alphanumeric chars)
    - Fine-grained tokens: github_pat_... (82 chars total)
    - OAuth tokens: gho_... (36 chars total)
    - Installation tokens: ghs_... (36 chars total)
    - GitHub App tokens: ghu_... (36 chars total)
    - Refresh tokens: ghr_... (76 chars total)

    Note: This only validates format, not authenticity or permissions.

    Args:
        token: GitHub token to validate

    Returns:
        True if valid format, False otherwise

    Examples:
        >>> validate_github_token("ghp_" + "A" * 36)
        True
        >>> validate_github_token("invalid_token")
        False
        >>> validate_github_token("")
        False
    """
    if not token or not isinstance(token, str):
        return False

    # Remove whitespace
    token = token.strip()

    if not token:
        return False

    # Check for known GitHub token prefixes and lengths
    # Classic personal access tokens: ghp_... (40 chars)
    if token.startswith('ghp_'):
        return len(token) == 40 and token[4:].isalnum()

    # Fine-grained personal access tokens: github_pat_... (82 chars)
    if token.startswith('github_pat_'):
        return len(token) == 82 and token[len('github_pat_'):].isalnum()

    # OAuth access tokens: gho_... (36 chars)
    if token.startswith('gho_'):
        return len(token) == 36 and token[4:].isalnum()

    # Installation access tokens: ghs_... (36 chars)
    if token.startswith('ghs_'):
        return len(token) == 36 and token[4:].isalnum()

    # GitHub App tokens: ghu_... (36 chars)
    if token.startswith('ghu_'):
        return len(token) == 36 and token[4:].isalnum()

    # Refresh tokens: ghr_... (76 chars)
    if token.startswith('ghr_'):
        return len(token) == 76 and token[4:].isalnum()

    # If no known prefix, reject (GitHub tokens always have prefixes)
    return False


def validate_server_config(config: Dict[str, Any]) -> List[str]:
    """
    Validate MCP server configuration structure and return errors.

    Required structure:
    {
        "command": str,  # Required: executable command
        "args": list,    # Required: command arguments
        "env": dict,     # Optional: environment variables
    }

    Args:
        config: Server configuration dictionary

    Returns:
        List of error messages (empty if valid)

    Examples:
        >>> validate_server_config({"command": "npx", "args": ["-y", "pkg"]})
        []
        >>> validate_server_config({"command": "npx"})
        ['Missing required field: args']
        >>> validate_server_config({})
        ['Missing required field: command', 'Missing required field: args']
    """
    errors = []

    # Check if config is a dictionary
    if not isinstance(config, dict):
        return ["Server configuration must be a dictionary"]

    # Check required field: command
    if 'command' not in config:
        errors.append("Missing required field: command")
    elif not isinstance(config['command'], str):
        errors.append("Field 'command' must be a string")
    elif not config['command'].strip():
        errors.append("Field 'command' cannot be empty")

    # Check required field: args
    if 'args' not in config:
        errors.append("Missing required field: args")
    elif not isinstance(config['args'], list):
        errors.append("Field 'args' must be a list")
    else:
        # Validate args are all strings
        for i, arg in enumerate(config['args']):
            if not isinstance(arg, str):
                errors.append(f"Argument at index {i} must be a string, got {type(arg).__name__}")

    # Check optional field: env
    if 'env' in config:
        if not isinstance(config['env'], dict):
            errors.append("Field 'env' must be a dictionary")
        else:
            # Validate env structure with detailed error reporting
            env_dict = config['env']

            for key, value in env_dict.items():
                # Validate key format using compiled pattern
                if not isinstance(key, str):
                    errors.append(f"Environment variable key {repr(key)} must be a string")
                elif not ENV_VAR_PATTERN.match(key):
                    errors.append(f"Environment variable key '{key}' has invalid format (must start with letter/underscore, contain only letters/numbers/underscores)")
                # Validate value format
                elif isinstance(value, str):
                    # Simple format is valid
                    pass
                elif isinstance(value, dict):
                    # Structured format validation
                    if 'value' not in value:
                        errors.append(f"Environment variable '{key}' structured format missing required 'value' field")
                    elif not isinstance(value['value'], str):
                        errors.append(f"Environment variable '{key}' value must be a string, got {type(value['value']).__name__}")
                    # description is optional, but if present must be a string
                    if 'description' in value and not isinstance(value['description'], str):
                        errors.append(f"Environment variable '{key}' description must be a string, got {type(value['description']).__name__}")
                else:
                    # Invalid value type
                    errors.append(f"Environment variable '{key}' value must be a string or dict with 'value' field, got {type(value).__name__}")

    return errors


def validate_env_dict(env: Dict[str, Any]) -> bool:
    """
    Validate environment variables dictionary format.

    Valid formats:
    1. Simple: {"KEY": "value"}
    2. Structured: {"KEY": {"value": "val", "description": "desc"}}
    3. Mixed: both formats can coexist

    Keys must be valid environment variable names:
    - Start with letter or underscore
    - Contain only letters, numbers, underscores
    - All uppercase recommended but not required

    Args:
        env: Environment dictionary to validate

    Returns:
        True if valid, False otherwise

    Examples:
        >>> validate_env_dict({"API_KEY": "secret"})
        True
        >>> validate_env_dict({"API_KEY": {"value": "secret"}})
        True
        >>> validate_env_dict({"123_INVALID": "value"})
        False
        >>> validate_env_dict({"KEY": 123})
        False
    """
    if not isinstance(env, dict):
        return False

    for key, value in env.items():
        # Validate key format using compiled pattern
        if not isinstance(key, str) or not ENV_VAR_PATTERN.match(key):
            return False

        # Validate value format
        if isinstance(value, str):
            # Simple format: {"KEY": "value"}
            continue
        elif isinstance(value, dict):
            # Structured format: {"KEY": {"value": "...", "description": "..."}}
            if 'value' not in value:
                return False
            if not isinstance(value['value'], str):
                return False
            # description is optional, but if present must be a string
            if 'description' in value and not isinstance(value['description'], str):
                return False
        else:
            # Invalid value type
            return False

    return True


def validate_mcpservers_config(config: Dict[str, Any]) -> List[str]:
    """
    Validate complete mcpServers configuration structure.

    Expected structure:
    {
        "mcpServers": {
            "server-name": {
                "command": "...",
                "args": [...],
                "env": {...}
            }
        }
    }

    Args:
        config: Complete configuration dictionary

    Returns:
        List of error messages (empty if valid)

    Examples:
        >>> config = {
        ...     "mcpServers": {
        ...         "filesystem": {
        ...             "command": "npx",
        ...             "args": ["-y", "@modelcontextprotocol/server-filesystem"]
        ...         }
        ...     }
        ... }
        >>> validate_mcpservers_config(config)
        []
    """
    errors = []

    # Check if config is a dictionary
    if not isinstance(config, dict):
        return ["Configuration must be a dictionary"]

    # Check for mcpServers key
    if 'mcpServers' not in config:
        return ["Missing required field: mcpServers"]

    mcp_servers = config['mcpServers']

    # Check mcpServers is a dictionary
    if not isinstance(mcp_servers, dict):
        return ["Field 'mcpServers' must be a dictionary"]

    # Check mcpServers is not empty
    if not mcp_servers:
        errors.append("Field 'mcpServers' cannot be empty")
        return errors

    # Validate each server configuration
    for server_name, server_config in mcp_servers.items():
        # Validate server name
        if not isinstance(server_name, str) or not server_name.strip():
            errors.append(f"Invalid server name: '{server_name}'")
            continue

        # Validate server configuration
        server_errors = validate_server_config(server_config)
        for error in server_errors:
            errors.append(f"Server '{server_name}': {error}")

    return errors


def is_valid_package_version(version: str) -> bool:
    """
    Validate semantic versioning format.

    Valid formats:
    - X.Y.Z (e.g., 1.0.0, 2.5.1)
    - vX.Y.Z (e.g., v1.0.0)
    - X.Y.Z-prerelease (e.g., 1.0.0-alpha, 1.0.0-beta.1)
    - latest

    Args:
        version: Version string to validate

    Returns:
        True if valid version format, False otherwise

    Examples:
        >>> is_valid_package_version("1.0.0")
        True
        >>> is_valid_package_version("v2.5.1")
        True
        >>> is_valid_package_version("1.0.0-beta")
        True
        >>> is_valid_package_version("latest")
        True
        >>> is_valid_package_version("invalid")
        False
    """
    if not version or not isinstance(version, str):
        return False

    # Special case: "latest" is valid
    if version == "latest":
        return True

    # Remove optional 'v' prefix
    if version.startswith('v'):
        version = version[1:]

    # Use compiled pattern for performance
    return bool(VERSION_PATTERN.match(version))
