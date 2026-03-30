"""
Centralized validation logic for FluidMCP API.

This module consolidates all validation functions used throughout the API
to ensure consistency and maintainability.
"""
from typing import Any, Dict
import re


def validate_temperature(temp: Any) -> None:
    """Validate temperature parameter for LLM inference."""
    if not isinstance(temp, (int, float)) or temp < 0 or temp > 2:
        raise ValueError("temperature must be a number between 0 and 2")


def validate_max_tokens(tokens: Any) -> None:
    """Validate max_tokens parameter for LLM inference."""
    if not isinstance(tokens, int) or tokens < 1 or tokens > 100000:
        raise ValueError("max_tokens must be an integer between 1 and 100000")


def validate_top_p(top_p: Any) -> None:
    """Validate top_p parameter for LLM inference."""
    if not isinstance(top_p, (int, float)) or top_p < 0 or top_p > 1:
        raise ValueError("top_p must be a number between 0 and 1")


def validate_inference_params(params: Dict[str, Any]) -> None:
    """
    Validate inference parameters.
    
    Args:
        params: Dictionary of inference parameters
        
    Raises:
        ValueError: If any parameter is invalid
    """
    if "temperature" in params:
        validate_temperature(params["temperature"])
    if "max_tokens" in params:
        validate_max_tokens(params["max_tokens"])
    if "top_p" in params:
        validate_top_p(params["top_p"])


def validate_env_variables(
    env: Dict[str, str],
    max_vars: int = 100,
    max_key_length: int = 256,
    max_value_length: int = 10240
) -> None:
    """
    Validate environment variables for security.
    
    Args:
        env: Dictionary of environment variables
        max_vars: Maximum number of variables allowed
        max_key_length: Maximum length of variable name
        max_value_length: Maximum length of variable value
        
    Raises:
        ValueError: If validation fails
    """
    if not isinstance(env, dict):
        raise ValueError("env must be a dictionary")
    
    if len(env) > max_vars:
        raise ValueError(f"Too many environment variables (max {max_vars})")
    
    # Validate each key-value pair
    for key, value in env.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("Environment variable keys and values must be strings")
        
        if len(key) > max_key_length:
            raise ValueError(f"Environment variable name too long (max {max_key_length} chars)")
        
        if len(value) > max_value_length:
            raise ValueError(f"Environment variable value too long (max {max_value_length} chars)")
        
        # Validate env var name (alphanumeric + underscore only, must start with letter/underscore)
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', key):
            raise ValueError(f"Invalid environment variable name: {key}")


def validate_server_config(config: Dict[str, Any]) -> None:
    """
    Validate server configuration for security and correctness.
    
    Args:
        config: Server configuration dictionary
        
    Raises:
        ValueError: If validation fails
    """
    if not isinstance(config, dict):
        raise ValueError("config must be a dictionary")
    
    # Validate required fields
    if "name" not in config:
        raise ValueError("Server name is required")
    
    if "command" not in config:
        raise ValueError("Server command is required")
    
    # Validate command
    command = config.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("command must be a non-empty string")
    
    # Validate args if present
    args = config.get("args", [])
    if not isinstance(args, list):
        raise ValueError("args must be a list")
    
    for i, arg in enumerate(args):
        if not isinstance(arg, str):
            raise ValueError(f"args[{i}] must be a string")
        
        # Check for shell injection patterns
        dangerous_patterns = [';', '&&', '||', '`', '$', '>', '<', '|']
        if any(pattern in arg for pattern in dangerous_patterns):
            # Allow these patterns only in specific flag contexts
            if not (arg.startswith('--') and '=' in arg):
                raise ValueError(f"args[{i}] contains potentially dangerous shell characters")
    
    # Validate env if present
    env = config.get("env", {})
    if env:
        validate_env_variables(env)


def validate_model_id(model_id: str) -> None:
    """
    Validate model ID format.
    
    Args:
        model_id: Model identifier
        
    Raises:
        ValueError: If model_id is invalid
    """
    if not isinstance(model_id, str):
        raise ValueError("model_id must be a string")
    
    if not model_id.strip():
        raise ValueError("model_id cannot be empty")
    
    if len(model_id) > 256:
        raise ValueError("model_id too long (max 256 chars)")
    
    # Allow alphanumeric, dash, underscore, slash (for provider/model format)
    if not re.match(r'^[A-Za-z0-9_/-]+$', model_id):
        raise ValueError("model_id contains invalid characters")


def validate_updatable_model_fields(updates: Dict[str, Any]) -> None:
    """
    Validate fields that can be updated for a model.
    
    Args:
        updates: Dictionary of fields to update
        
    Raises:
        ValueError: If any field is invalid
    """
    # Validate updatable fields
    allowed_update_fields = {
        "model", "api_key", "default_params", "timeout", "max_retries",
        "endpoints", "restart_policy", "max_restarts", "restart_delay"
    }
    
    invalid_fields = set(updates.keys()) - allowed_update_fields
    if invalid_fields:
        raise ValueError(f"Cannot update fields: {invalid_fields}")
    
    # Validate field values
    if "default_params" in updates:
        validate_inference_params(updates["default_params"])
    
    if "timeout" in updates:
        timeout = updates["timeout"]
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("timeout must be a positive number")
    
    if "max_retries" in updates:
        max_retries = updates["max_retries"]
        if not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
