"""
Reusable validation utilities for FluidAI MCP services.
"""

import re
from typing import Dict, List


PACKAGE_PATTERN = re.compile(
    r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+@(latest|[0-9]+\.[0-9]+\.[0-9]+)$"
)


def validate_package_string(s: str) -> bool:
    """
    Validate package string format: Author/Package@version

    Examples:
    - Author/Package@1.0.0
    - Author/Package@latest
    """
    if not isinstance(s, str):
        return False
    return bool(PACKAGE_PATTERN.match(s))


def validate_port_number(port: int) -> bool:
    """
    Validate TCP/UDP port number.
    Valid range: 1 - 65535
    """
    if not isinstance(port, int):
        return False
    return 1 <= port <= 65535


def validate_github_token(token: str) -> bool:
    """
    Validate GitHub token.
    Must be a non-empty string.
    """
    if not isinstance(token, str):
        return False
    return bool(token.strip())


def validate_server_config(config: Dict) -> List[str]:
    """
    Validate MCP server configuration block.

    Expected structure:
    {
        "command": "...",
        "args": [...]
    }

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: List[str] = []

    if not isinstance(config, dict):
        return ["Server config must be a dictionary"]

    if "command" not in config:
        errors.append("Missing required field: command")
    elif not isinstance(config["command"], str):
        errors.append("Field 'command' must be a string")

    if "args" not in config:
        errors.append("Missing required field: args")
    elif not isinstance(config["args"], list):
        errors.append("Field 'args' must be a list")

    return errors


def validate_env_dict(env: Dict) -> bool:
    """
    Validate environment variable dictionary.

    Expected:
    {
        "KEY": "value"
    }
    """
    if not isinstance(env, dict):
        return False

    for key, value in env.items():
        if not isinstance(key, str):
            return False
        if not isinstance(value, (str, int, float)):
            return False

    return True
