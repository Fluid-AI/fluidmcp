"""
Management API endpoints for dynamic MCP server control.

Provides REST API for:
- Adding/removing server configurations
- Starting/stopping/restarting servers
- Querying server status and logs
- Listing all configured servers
- Replicate model inference
"""
from typing import Dict, Any, Optional, Literal, List, Tuple
from fastapi import APIRouter, Request, HTTPException, Body, Query, Depends, Response
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator, ConfigDict
from loguru import logger
import os
import asyncio
import httpx
import time
import json
import threading
from collections import defaultdict
from time import time as current_time
from datetime import datetime

# Import centralized validators
from .validators import (
    validate_temperature,
    validate_max_tokens,
    validate_top_p,
    validate_inference_params,
    validate_env_variables,
    validate_server_config,
    validate_model_id,
    validate_updatable_model_fields
)

# Import rate limiter utilities
from ..utils.rate_limiter import check_rate_limit, get_rate_limiter_stats, clear_rate_limiter

# COPILOT COMMENT 2 FIX: Simplified DuplicateKeyError import pattern
# Import custom DuplicateKeyError from base module (eliminates pymongo dependency)
# All backends (MongoDB, in-memory) raise this exception for duplicate key violations
from ..repositories.base import DuplicateKeyError

# Optional Redis support for distributed rate limiting
try:
    import redis.asyncio as redis
    _redis_available = True
except ImportError:
    redis = None
    _redis_available = False

from ..services.llm_provider_registry import get_model_type, get_model_config, list_models_by_type
from ..services.replicate_openai_adapter import replicate_chat_completion
from ..services.replicate_client import ReplicateClient, get_replicate_client
from ..services.llm_metrics import get_metrics_collector
from ..services import omni_adapter

from ..utils.env_utils import is_placeholder, has_env_var_syntax

router = APIRouter()
security = HTTPBearer(auto_error=False)

# Constants
MAX_ERROR_MESSAGE_LENGTH = 1000  # Limit error messages to prevent DoS via large responses and protect sensitive data

# LOW PRIORITY FIX #12: Rate limit configurations (requests, window_seconds)
RATE_LIMIT_MODEL_REGISTRATION = (10, 60)   # 10 req/min - restrictive for resource-intensive operation
RATE_LIMIT_MODEL_UPDATE = (20, 60)         # 20 req/min - moderate for config changes
RATE_LIMIT_MODEL_DELETE = (20, 60)         # 20 req/min - moderate for destructive operation
RATE_LIMIT_MODEL_ROLLBACK = (10, 60)       # 10 req/min - restrictive for destructive operation
RATE_LIMIT_MODEL_LIST = (60, 60)           # 60 req/min - permissive for read operation
# CRITICAL FIX: Add rate limits for inference endpoints to prevent DDoS attacks
RATE_LIMIT_CHAT_COMPLETIONS = (60, 60)     # 60 req/min - permissive for production inference
RATE_LIMIT_COMPLETIONS = (60, 60)          # 60 req/min - permissive for production inference
RATE_LIMIT_MODELS_GET = (120, 60)          # 120 req/min - very permissive for metadata reads


def truncate_error(error_msg: str) -> str:
    """
    Truncate error message to MAX_ERROR_MESSAGE_LENGTH to prevent DoS and info leakage.

    Args:
        error_msg: Error message to truncate

    Returns:
        Truncated error message with ellipsis if needed
    """
    if len(error_msg) > MAX_ERROR_MESSAGE_LENGTH:
        return error_msg[:MAX_ERROR_MESSAGE_LENGTH] + "... (truncated)"
    return error_msg


def sanitize_audit_changes(changes: Dict[str, Any]) -> Dict[str, Any]:
    """
    Redact sensitive fields from audit log changes to prevent credential leakage.

    Args:
        changes: Dictionary of changes to sanitize

    Returns:
        Sanitized dictionary with sensitive fields redacted
    """
    sensitive_fields = {"api_key", "api_token", "auth_token", "password", "secret", "token", "bearer_token"}

    sanitized = {}
    for key, value in changes.items():
        if isinstance(value, dict):
            # Recursively sanitize nested dictionaries
            sanitized[key] = {
                k: "***REDACTED***" if k.lower() in sensitive_fields else v
                for k, v in value.items()
            }
        elif key.lower() in sensitive_fields:
            sanitized[key] = "***REDACTED***"
        else:
            sanitized[key] = value

    return sanitized


def sanitize_error_message(error_msg: str) -> str:
    """
    CRITICAL SECURITY: Redact sensitive data patterns from error messages.

    Prevents API keys, tokens, and other secrets from being exposed in logs,
    exception messages, and HTTP responses.

    Detects and redacts:
    - Replicate API keys (r8_...)
    - Generic tokens starting with sk_, pk_, tok_, key_
    - Bearer tokens
    - Long alphanumeric strings that look like credentials (20+ chars)

    Args:
        error_msg: Error message string that may contain sensitive data

    Returns:
        Sanitized error message with credentials redacted
    """
    import re

    if not isinstance(error_msg, str):
        return str(error_msg)

    # Redact Replicate API keys (r8_followed by alphanumeric)
    error_msg = re.sub(r'\br8_[A-Za-z0-9]{20,}\b', 'r8_***REDACTED***', error_msg)

    # Redact common API key patterns (sk_, pk_, tok_, key_ prefixes)
    error_msg = re.sub(r'\b(sk|pk|tok|key)_[A-Za-z0-9_-]{10,}\b', r'\1_***REDACTED***', error_msg, flags=re.IGNORECASE)

    # Redact Bearer tokens
    error_msg = re.sub(r'Bearer\s+[A-Za-z0-9_\-\.]{20,}', 'Bearer ***REDACTED***', error_msg, flags=re.IGNORECASE)

    # Redact long alphanumeric strings that look like tokens (20+ chars, mixed case/numbers)
    # But only if they contain both letters and numbers (to avoid false positives with regular words)
    error_msg = re.sub(
        r'\b(?=.*[A-Za-z])(?=.*[0-9])[A-Za-z0-9_\-\.]{20,}\b',
        '***REDACTED***',
        error_msg
    )

    return error_msg


def get_client_ip(request: Request) -> str:
    """
    Extract client IP address with proxy support.

    Checks X-Forwarded-For header first (for requests behind proxies/load balancers),
    then falls back to direct connection IP.

    Args:
        request: FastAPI Request object

    Returns:
        Client IP address string, or "unknown" if not available
    """
    # Check X-Forwarded-For header first (if behind trusted proxy)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take first IP (original client), strip whitespace
        return forwarded_for.split(",")[0].strip()

    # Fall back to direct connection IP
    return request.client.host if request.client else "unknown"


def get_rate_limit_key(action: str, token: str, client_ip: str) -> str:
    """
    Generate a composite rate limit key using both token and IP address.

    This prevents rate limit bypass scenarios where multiple users share the same IP
    (e.g., behind NAT, corporate proxy, or load balancer).

    Args:
        action: Action being rate limited (e.g., "register_model", "update_model")
        token: Bearer token for authentication
        client_ip: Client IP address

    Returns:
        Rate limit key in format: "action:token_hash:ip"
    """
    import hashlib

    # Hash token to avoid logging sensitive data
    # Handle None token (insecure mode)
    if token is None:
        token_hash = "insecure"
    else:
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]

    return f"{action}:{token_hash}:{client_ip}"


# ==================== Rate Limiting ====================
# Rate limiting implementation has been moved to fluidmcp/cli/utils/rate_limiter.py
# Import check_rate_limit, get_rate_limiter_stats, clear_rate_limiter from that module


# ==================== Audit Logging ====================

async def log_audit_event(
    db: Any,
    action: str,
    model_id: str,
    client_ip: str,
    changes: Optional[Dict[str, Any]] = None,
    status: str = "success",
    error_message: Optional[str] = None
):
    """
    Log model operation to audit trail for security compliance and forensics.

    Args:
        db: Database manager instance
        action: Operation performed (register_model, update_model, delete_model)
        model_id: Model identifier
        client_ip: Client IP address
        changes: Optional dict of changes made
        status: Operation status (success, failure)
        error_message: Optional error message if status is failure
    """
    if not hasattr(db, 'db') or db.db is None:
        # No MongoDB available - log to file only
        logger.info(
            f"AUDIT: action={action} model_id={model_id} client={client_ip} "
            f"status={status} changes={changes}"
        )
        return

    try:
        audit_entry = {
            "action": action,
            "model_id": model_id,
            "client_ip": client_ip,
            "timestamp": datetime.utcnow(),
            "status": status,
        }

        if changes:
            audit_entry["changes"] = changes

        if error_message:
            audit_entry["error_message"] = error_message

        await db.db.fluidmcp_audit_log.insert_one(audit_entry)
        logger.debug(f"Audit log recorded: {action} on model '{model_id}' by {client_ip}")
    except Exception as e:
        # Audit logging should never break the main operation
        # CRITICAL SECURITY: Sanitize error message to prevent API key exposure
        sanitized_error = sanitize_error_message(str(e))
        logger.error(f"Failed to write audit log (non-fatal): {sanitized_error}")


# ==================== Shared Validation Functions ====================

# Validation functions moved to validators.py module for consolidation


# ==================== Pydantic Models for Request Validation ====================

class ReplicateModelConfig(BaseModel):
    """Validation model for Replicate LLM model registration."""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "model_id": "llama-4-maverick",
                "type": "replicate",
                "model": "meta/llama-4-maverick-instruct",
                "api_key": "${REPLICATE_API_TOKEN}",
                "default_params": {
                    "temperature": 0.7,
                    "max_tokens": 4096,
                    "top_p": 0.9
                },
                "timeout": 300,
                "max_retries": 3,
                "capabilities": []
            }
        }
    )

    model_id: str = Field(
        ...,
        min_length=2,
        max_length=100,
        pattern="^[a-zA-Z0-9_-]+$",
        description="Unique model identifier (alphanumeric, dash, underscore only; minimum 2 characters)"
    )
    type: Literal["replicate"] = Field(..., description="Model provider type")
    model: str = Field(
        ...,
        min_length=1,
        max_length=255,
        pattern="^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(:[a-zA-Z0-9_.-]+)?$",
        description="Replicate model name in the form owner/model-name or owner/model-name:version (e.g., meta/llama-4-maverick-instruct, black-forest-labs/flux-1.1-pro)"
    )
    api_key: str = Field(..., min_length=1, max_length=500, description="Replicate API token (use ${ENV_VAR} placeholder)")
    default_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Default inference parameters (temperature, max_tokens, etc.)"
    )
    timeout: int = Field(default=300, ge=10, le=3600, description="Request timeout in seconds")
    max_retries: int = Field(default=3, ge=0, le=10, description="Maximum retry attempts")
    capabilities: List[str] = Field(
        default_factory=list,
        description="Model capabilities (e.g., ['text-to-image', 'text-to-video'])"
    )

    @field_validator('api_key')
    @classmethod
    def validate_api_key(cls, v):
        """
        Validate API key uses environment variable syntax.

        Security requirement: API keys must not be stored as raw values in configuration
        to prevent credential exposure in logs, backups, or version control.
        """
        if v and not has_env_var_syntax(v):
            raise ValueError(
                "api_key must use environment variable placeholders for security "
                "(e.g., '${REPLICATE_API_TOKEN}' or '$API_KEY'). "
                "Raw API keys are not accepted to prevent credential exposure in configuration."
            )
        return v

    @field_validator('default_params')
    @classmethod
    def validate_params(cls, v):
        """Validate allowed parameter keys."""
        allowed_keys = {'temperature', 'max_tokens', 'top_p', 'top_k', 'stop', 'frequency_penalty', 'presence_penalty'}
        invalid = set(v.keys()) - allowed_keys
        if invalid:
            raise ValueError(f"Invalid parameters: {invalid}. Allowed: {allowed_keys}")

        # Validate parameter ranges using shared validation functions
        try:
            validate_inference_params(v)
        except ValueError as e:
            # CRITICAL SECURITY: Sanitize error message to prevent API key exposure
            raise ValueError(sanitize_error_message(str(e)))

        return v


# Shared HTTP client for vLLM proxy requests (lazy-initialized for connection pooling)
_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    """
    Get or create the shared HTTP client (lazy initialization).

    Lazy initialization prevents resource leaks when the module is imported
    but the client is never used (e.g., in Replicate-only or test configurations).
    """
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=300.0)
    return _http_client


async def cleanup_http_client():
    """Close the shared HTTP client to prevent resource leaks."""
    global _http_client
    if _http_client is not None:
        try:
            await _http_client.aclose()
        except Exception as e:
            logger.error(f"Error closing management HTTP client: {e}")
        finally:
            # Always clear the reference so the client can be recreated if needed
            _http_client = None


def get_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate bearer token if secure mode is enabled"""
    bearer_token = os.environ.get("FMCP_BEARER_TOKEN")
    secure_mode = os.environ.get("FMCP_SECURE_MODE") == "true"

    if not secure_mode:
        return None
    if not credentials or credentials.scheme.lower() != "bearer" or credentials.credentials != bearer_token:
        raise HTTPException(status_code=401, detail="Invalid or missing authorization token")
    return credentials.credentials


def validate_env_variables(env: Dict[str, str], max_vars: int = 100, max_key_length: int = 256, max_value_length: int = 10240) -> None:
    """
    Validate environment variables to prevent injection attacks and DoS.

    Security context:
    - Environment variables are passed to subprocess.Popen() with shell=False
    - This means shell metacharacters (;, |, &, etc.) are NOT interpreted
    - Values are passed directly to the child process, no shell injection risk

    Security checks:
    - Prevent MongoDB injection (keys starting with $ or containing dots)
    - Prevent DoS via excessive data (length limits)
    - Validate key format (POSIX standard: alphanumeric + underscore only)
    - Check for null bytes (can cause issues in C-based processes)

    Args:
        env: Environment variables dict to validate
        max_vars: Maximum number of variables allowed (default: 100)
        max_key_length: Maximum key length (default: 256)
        max_value_length: Maximum value length (default: 10KB)

    Raises:
        HTTPException: If validation fails
    """
    import re

    # Check number of variables (DoS prevention)
    if len(env) > max_vars:
        raise HTTPException(400, f"Too many environment variables (max: {max_vars})")

    # Validate each key-value pair
    for key, value in env.items():
        # Type check
        if not isinstance(key, str) or not isinstance(value, str):
            raise HTTPException(400, "Environment variable keys and values must be strings")

        # Key length check (DoS prevention)
        if len(key) > max_key_length:
            raise HTTPException(400, f"Environment variable key too long (max: {max_key_length} chars): {key[:50]}...")

        # Value length check (DoS prevention)
        if len(value) > max_value_length:
            raise HTTPException(400, f"Environment variable value too long (max: {max_value_length} chars) for key: {key}")

        # MongoDB injection prevention - keys must not start with $ or contain dots
        if key.startswith('$'):
            raise HTTPException(400, f"Invalid environment variable key (MongoDB reserved): {key}")

        if '.' in key:
            raise HTTPException(400, f"Invalid environment variable key (contains dot): {key}")

        # Key format validation - only alphanumeric and underscore
        # Standard POSIX env var naming convention (no hyphens - not supported by bash/sh)
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', key):
            raise HTTPException(400, f"Invalid environment variable key format: {key}. Must start with letter or underscore and contain only alphanumeric and underscore characters.")

        # Null byte check - can cause issues in C-based processes
        if '\0' in value:
            raise HTTPException(400, f"Environment variable value contains null byte for key: {key}")


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Extract user identifier from bearer token.

    ⚠️  WARNING: NOT PRODUCTION READY ⚠️
    This implementation uses a SHA-256 hash of the bearer token as the user ID.
    For production use, implement proper JWT authentication with:
    - Token signature verification
    - Expiration checking
    - Role-based access control (RBAC)
    - User claims extraction (email, user_id, roles)

    Current behavior:
    - In secure mode: Uses SHA-256 hash of token as user ID
    - In non-secure mode: Returns "anonymous"

    Returns:
        User identifier string
    """
    secure_mode = os.environ.get("FMCP_SECURE_MODE") == "true"

    if not secure_mode:
        return "anonymous"

    if not credentials or not credentials.credentials:
        return "anonymous"

    # Use secure hash of token as user ID to avoid weak 8-char prefix
    # This provides better security than 8-char prefix but still needs JWT for production
    import hashlib
    token = credentials.credentials
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    user_id = f"user_{token_hash[:16]}"  # Use first 16 hex chars (64 bits) of hash

    return user_id


def get_server_manager(request: Request):
    """Dependency injection for ServerManager."""
    if not hasattr(request.app.state, "server_manager"):
        raise HTTPException(500, "ServerManager not initialized")
    return request.app.state.server_manager


def get_database_manager(request: Request):
    """Dependency injection for DatabaseManager."""
    if not hasattr(request.app.state, "db_manager") or request.app.state.db_manager is None:
        raise HTTPException(500, "DatabaseManager not initialized")
    return request.app.state.db_manager


def sanitize_input(value: Any) -> Any:
    """
    Sanitize user input to prevent MongoDB injection attacks.

    ⚠️  WARNING: This is a basic defense layer. For production:
    - Use MongoDB's query parameterization
    - Validate input types strictly at API boundaries
    - Use schema validation (Pydantic models)
    - Never construct queries by string concatenation

    This function:
    - Rejects dict keys that start with "$" (MongoDB-style operators)
    - Leaves string values unchanged (no escaping performed)
    - Recursively sanitizes nested dicts and lists

    Args:
        value: Input value to sanitize

    Returns:
        Sanitized value

    Raises:
        HTTPException: If MongoDB operator detected in dict keys
    """
    if isinstance(value, dict):
        # Check for MongoDB operators and dot notation in dictionary keys (most dangerous)
        for key in value.keys():
            if isinstance(key, str):
                if key.startswith("$"):
                    raise HTTPException(
                        400,
                        "MongoDB operator-style keys (starting with '$') are not allowed in input"
                    )
                if "." in key:
                    raise HTTPException(
                        400,
                        "Dictionary keys containing '.' (dot notation) are not allowed in input"
                    )
        # Recursively sanitize dictionary values
        return {k: sanitize_input(v) for k, v in value.items()}
    elif isinstance(value, list):
        # Recursively sanitize list items
        return [sanitize_input(item) for item in value]
    elif isinstance(value, str):
        # For string values, MongoDB operators are generally safe but can be escaped
        # Don't modify the string - let MongoDB handle it with parameterized queries
        # Removing $ or {} can break legitimate values
        return value
    else:
        # Primitive types (int, float, bool, None) are safe
        return value


def validate_server_config(config: Dict[str, Any]) -> None:
    """
    Validate server configuration to prevent command injection and ensure safety.

    Args:
        config: Server configuration dict

    Raises:
        HTTPException: If validation fails
    """
    import re

    # Validate required fields
    if "command" not in config:
        raise HTTPException(400, "Server configuration must include 'command' field")

    command = config["command"]

    # Command path validation - reject absolute paths
    if os.path.isabs(command):
        raise HTTPException(
            400,
            f"Absolute paths not allowed in command field. Use command name only: {command}"
        )

    # Command must not contain path separators
    if "/" in command or "\\" in command:
        raise HTTPException(
            400,
            f"Command must be a simple command name without path separators: {command}"
        )

    # Whitelist of allowed commands (can be extended via environment variable)
    allowed_commands_default = ["npx", "node", "python", "python3", "uv", "uvx", "docker", "deno", "bun"]
    allowed_commands_env = os.environ.get("FMCP_ALLOWED_COMMANDS", "").split(",")
    allowed_commands = allowed_commands_default + [cmd.strip() for cmd in allowed_commands_env if cmd.strip()]

    # Check if command is in whitelist
    if command not in allowed_commands:
        raise HTTPException(
            400,
            f"Command '{command}' is not allowed. Allowed commands: {', '.join(allowed_commands)}. "
            f"To add more commands, set FMCP_ALLOWED_COMMANDS environment variable."
        )

    # Validate args if present
    if "args" in config:
        args = config["args"]
        if not isinstance(args, list):
            raise HTTPException(400, "Server configuration 'args' must be a list")

        # Enhanced argument validation
        dangerous_patterns = [";", "&", "|", "`", "&&", "||", "$(", "${", "\n", "\r"]
        # Shell metacharacters that should be rejected unless in specific contexts
        shell_metacharacters = ["<", ">", ">>", "<<"]

        for arg in args:
            if not isinstance(arg, str):
                raise HTTPException(400, "All arguments must be strings")

            # Length validation - max 1000 chars per argument
            if len(arg) > 1000:
                raise HTTPException(
                    400,
                    f"Argument exceeds maximum length of 1000 characters: {arg[:50]}..."
                )

            # Check for dangerous shell patterns
            for pattern in dangerous_patterns:
                if pattern in arg:
                    raise HTTPException(
                        400,
                        f"Argument contains potentially dangerous pattern '{pattern}': {arg}"
                    )

            # Check for shell metacharacters (with exceptions for flags)
            for pattern in shell_metacharacters:
                if pattern in arg:
                    raise HTTPException(
                        400,
                        f"Argument contains shell metacharacter '{pattern}': {arg}"
                    )

            # Validate argument structure for flags
            if arg.startswith("-"):
                # Flags should match pattern: -x or --xxx or --xxx=value
                if not re.match(r"^-[a-zA-Z0-9]$|^--[a-zA-Z0-9-]+(=.+)?$", arg):
                    raise HTTPException(
                        400,
                        f"Invalid flag format: {arg}. Flags should be -x or --flag or --flag=value"
                    )

    # Validate env if present
    if "env" in config:
        env = config["env"]
        if not isinstance(env, dict):
            raise HTTPException(400, "Server configuration 'env' must be a dictionary")

        # Enhanced environment variable validation
        for key, value in env.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise HTTPException(400, "Environment variable keys and values must be strings")

            # Validate env var name (alphanumeric + underscore only)
            if not re.match(r"^[A-Z_][A-Z0-9_]*$", key):
                raise HTTPException(
                    400,
                    f"Invalid environment variable name '{key}'. Must be uppercase alphanumeric with underscores."
                )

            # Length validation - max 10,000 chars per value
            if len(value) > 10000:
                raise HTTPException(
                    400,
                    f"Environment variable '{key}' value exceeds maximum length of 10,000 characters"
                )

            # Check for shell metacharacters in env values
            dangerous_env_patterns = [";", "&", "|", "`", "$(", "${", "\n", "\r", "&&", "||"]
            for pattern in dangerous_env_patterns:
                if pattern in value:
                    raise HTTPException(
                        400,
                        f"Environment variable '{key}' contains dangerous pattern '{pattern}'"
                    )


# ==================== Configuration Management ====================

@router.post("/servers")
async def add_server(
    request: Request,
    config: Dict[str, Any] = Body(
        ...,
        example={
            "id": "filesystem",
            "name": "Filesystem Server",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
            "env": {},
            "working_dir": "/tmp",
            "install_path": "/tmp",
            "restart_policy": "on-failure",
            "max_restarts": 3
        }
    ),
    token: str = Depends(get_token)
):
    """
    Add a new server configuration.

    Request Body:
        id (str): Unique server identifier (URL-friendly)
        name (str): Human-readable display name
        command (str): Command to run
        args (list): Command arguments
        env (dict): Environment variables
        working_dir (str): Working directory
        install_path (str): Installation path
        restart_policy (str): 'no', 'on-failure', or 'always'
        max_restarts (int): Maximum restart attempts
    """
    manager = get_server_manager(request)

    # Sanitize input to prevent MongoDB injection
    config = sanitize_input(config)

    # Validate required fields
    if "id" not in config:
        raise HTTPException(400, "Server id is required")
    if "name" not in config:
        raise HTTPException(400, "Server name is required")

    # Validate configuration for security
    validate_server_config(config)

    id = config["id"]
    name = config["name"]

    # Check if server already exists (check both DB and in-memory)
    if id in manager.configs:
        raise HTTPException(400, f"Server with id '{id}' already exists")

    existing = await manager.db.get_server_config(id)
    if existing:
        raise HTTPException(400, f"Server with id '{id}' already exists")

    # Try to save to database, fall back to in-memory storage
    try:
        success = await manager.db.save_server_config(config)
        if not success:
            # Store in-memory as fallback
            logger.warning(f"Database save failed for '{name}', storing in-memory only")
    except DuplicateKeyError:
        # Race condition: another request created the same server concurrently
        raise HTTPException(409, f"Server with id '{id}' was created concurrently")

    # Always store in configs dict for immediate access
    manager.configs[id] = config

    logger.info(f"Added server configuration: {name} (id: {id})")
    return {
        "message": f"Server '{name}' configured successfully",
        "id": id,
        "name": name
    }


# ==================== GitHub Clone Helper ====================

async def _validate_server_with_manager(
    manager: Any,
    server_id: str,
    config: Dict[str, Any],
    timeout: int = 5,
) -> Tuple[bool, Optional[str]]:
    """
    Validate a server configuration by test-starting it through the manager lifecycle.

    This ensures we exercise the EXACT same runtime path as a real server start
    (env merging, working_dir resolution, MCP handshake, etc.).

    The server is added temporarily to the manager's in-memory registry, started,
    waited on for ``timeout`` seconds, then stopped and removed.  It is NOT saved
    to the database at any point during validation.

    Args:
        manager: ServerManager instance
        server_id: Server identifier (used as a temporary key)
        config: Flat server configuration dict
        timeout: Seconds to wait before checking if the server is still alive

    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        # 1. Register temporarily in manager (NOT in database)
        manager.configs[server_id] = config

        # 2. Start through manager (uses real lifecycle)
        logger.info(f"[validate] Test-starting server '{server_id}'...")
        success = await manager.start_server(server_id, config, user_id="validation")
        if not success:
            return False, "Server failed to start during validation"

        # 3. Wait for startup
        await asyncio.sleep(timeout)

        # 4. Check if still running
        status = await manager.get_server_status(server_id)
        is_running = status.get("state") == "running"

        # 5. Stop server
        logger.info(f"[validate] Stopping test server '{server_id}'...")
        await manager.stop_server(server_id, force=False)

        # 6. Remove temporary entry
        manager.configs.pop(server_id, None)

        if not is_running:
            return False, "Server crashed immediately after startup"

        return True, None

    except Exception as e:
        logger.error(f"[validate] Validation failed for '{server_id}': {e}")
        # Best-effort cleanup
        try:
            await manager.stop_server(server_id, force=True)
        except Exception:
            pass
        manager.configs.pop(server_id, None)
        return False, str(e)


@router.post("/servers/from-github")
async def add_server_from_github(
    request: Request,
    config: Dict[str, Any] = Body(
        ...,
        example={
            "github_repo": "anthropics/mcp-server-example",
            "branch": "main",
            "server_id": "example-server",
            "env": {},
            "enabled": True,
            "restart_policy": "on-failure",
            "test_before_save": True,
        },
    ),
    token: str = Depends(get_token),
):
    """
    Clone a GitHub repository and add the MCP server(s) it contains.

    **Authentication**: Requires ``X-GitHub-Token`` header with a valid GitHub PAT
    in addition to the usual ``Authorization: Bearer`` token.

    **Workflow**:
    1. Clone / update repository from GitHub
    2. Extract metadata (``metadata.json`` or README fallback)
    3. Validate each server's command against the allowlist
    4. Optionally test-start each server through the manager lifecycle
    5. Save to database

    **Single-server repos**: the provided ``server_id`` is used directly.

    **Multi-server repos**: IDs are generated as ``{server_id}-{slugified-name}``.
    Use ``server_name`` to select a single server.

    **Headers**:
    - ``X-GitHub-Token``: GitHub personal access token (required)

    **Request body fields**:
    - ``github_repo``: ``owner/repo`` or full URL
    - ``branch``: branch to clone (default: ``"main"``)
    - ``server_id``: base server identifier (lowercase alphanumeric + hyphens)
    - ``server_name``: select a specific server from a multi-server repo
    - ``env``: additional environment variables
    - ``enabled``: whether to enable the server(s) (default: ``true``)
    - ``restart_policy``: ``never`` | ``on-failure`` | ``always``
    - ``max_restarts``: max restart attempts (0–10)
    - ``test_before_save``: validate via test-start before persisting (default: ``true``)
    """
    from ..services.github_utils import GitHubService
    from ..services.validators import validate_command_allowlist  # noqa: F401 – used inside GitHubService

    manager = get_server_manager(request)
    user_id = get_current_user(request)

    # 1. Require GitHub token in header (never in request body to avoid logging)
    github_token = request.headers.get("X-GitHub-Token")
    if not github_token:
        raise HTTPException(
            400,
            "X-GitHub-Token header is required. "
            "Provide your GitHub personal access token in the request header.",
        )

    # 2. Sanitise input to prevent MongoDB injection
    config = sanitize_input(config)

    # 3. Validate required fields
    github_repo = config.get("github_repo")
    base_server_id = config.get("server_id")

    if not github_repo:
        raise HTTPException(400, "github_repo is required")
    if not base_server_id:
        raise HTTPException(400, "server_id is required")

    branch = config.get("branch", "main")
    server_name = config.get("server_name")
    subdirectory = config.get("subdirectory")
    env = config.get("env", {})
    restart_policy = config.get("restart_policy", "never")
    max_restarts = int(config.get("max_restarts", 3))
    enabled = bool(config.get("enabled", True))
    test_before_save = bool(config.get("test_before_save", True))

    # Validate env variables if provided
    if env:
        validate_env_variables(env)

    try:
        # 4. Clone / update and build server config(s)
        logger.info(f"Building server config(s) from {github_repo}@{branch}"
                    + (f" subdirectory={subdirectory}" if subdirectory else ""))
        server_configs, clone_path = GitHubService.build_server_configs(
            repo_path=github_repo,
            token=github_token,
            base_server_id=base_server_id,
            branch=branch,
            server_name=server_name,
            subdirectory=subdirectory,
            env=env,
            restart_policy=restart_policy,
            max_restarts=max_restarts,
            enabled=enabled,
            created_by=user_id,
        )
        logger.info(f"Built {len(server_configs)} server config(s) from {github_repo}")

        # 5. Validate, optionally test-start, and persist each server
        results = []
        for server_config in server_configs:
            sid = server_config["id"]
            display_name = server_config.get("name", sid)

            # Duplicate check – in-memory and database
            if sid in manager.configs:
                raise HTTPException(409, f"Server '{sid}' already exists")
            existing = await manager.db.get_server_config(sid)
            if existing:
                raise HTTPException(409, f"Server '{sid}' already exists in database")

            # Validate command and args for security (env is skipped here because
            # metadata.json from GitHub repos may use non-uppercase env key names,
            # e.g. Google service account fields like "type", "project_id").
            # The command allowlist is already enforced by GitHubService.
            command_only = {k: v for k, v in server_config.items() if k != "env"}
            validate_server_config(command_only)

            # Optional test-start through manager lifecycle
            if test_before_save:
                logger.info(f"Test-starting '{sid}' for validation...")
                ok, err = await _validate_server_with_manager(manager, sid, server_config, timeout=5)
                if not ok:
                    raise HTTPException(
                        400,
                        f"Server '{display_name}' failed validation: {truncate_error(err or 'unknown error')}",
                    )
                logger.info(f"Server '{sid}' validated successfully")

            # Persist to database
            try:
                await manager.db.save_server_config(server_config)
            except DuplicateKeyError:
                raise HTTPException(409, f"Server '{sid}' was created concurrently")

            # Register in manager's in-memory configs for immediate availability
            manager.configs[sid] = server_config

            results.append({
                "id": sid,
                "name": display_name,
                "status": "validated" if test_before_save else "added",
            })
            logger.info(f"Added GitHub server: {display_name} (id: {sid})")

        # 6. Return response
        return {
            "message": f"Successfully added {len(results)} server(s) from GitHub repository",
            "servers": results,
            "repository": github_repo,
            "branch": branch,
            "clone_path": str(clone_path),
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, truncate_error(str(e)))
    except RuntimeError as e:
        raise HTTPException(502, truncate_error(str(e)))
    except Exception as e:
        logger.exception(f"Unexpected error adding server from GitHub: {e}")
        raise HTTPException(500, f"Internal error: {truncate_error(str(e))}")


@router.get("/servers")
async def list_servers(request: Request, enabled_only: bool = True, include_deleted: bool = False):
    """
    List all configured servers with their status.

    Args:
        enabled_only: If True (default), only return enabled servers. If False, return all including disabled.
        include_deleted: If True, include soft-deleted servers (for admin recovery). Default: False.

    Returns:
        List of servers with config and status
    """
    manager = get_server_manager(request)
    servers = await manager.list_servers(enabled_only=enabled_only, include_deleted=include_deleted)

    return {
        "servers": servers,
        "count": len(servers)
    }


@router.get("/servers/{id}")
async def get_server(request: Request, id: str):
    """
    Get detailed information about a specific server.

    Args:
        id: Server identifier

    Returns:
        Server config and status
    """
    manager = get_server_manager(request)

    # Get config from in-memory or database
    config = manager.configs.get(id)
    if not config:
        config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    # Get status
    status = await manager.get_server_status(id)

    return {
        "id": id,
        "name": config.get("name"),
        "config": config,
        "status": status
    }


@router.put("/servers/{id}")
async def update_server(
    request: Request,
    id: str,
    config: Dict[str, Any] = Body(...),
    token: str = Depends(get_token)
):
    """
    Update server configuration (only when stopped).

    Args:
        id: Server identifier
        config: New configuration (must include 'name' and 'command' fields)

    Required Fields:
        name (str): Human-readable display name
        command (str): Command to run (must be whitelisted)

    Optional Fields:
        args (list): Command arguments
        env (dict): Environment variables
        description (str): Server description
        enabled (bool): Whether server is enabled
        restart_policy (str): 'no', 'on-failure', or 'always'
        max_restarts (int): Maximum restart attempts
        working_dir (str): Working directory
        install_path (str): Installation path

    Returns:
        Success message
    """
    manager = get_server_manager(request)

    # Sanitize input to prevent MongoDB injection
    config = sanitize_input(config)

    # Check if server exists (in-memory or database)
    existing = manager.configs.get(id)
    if not existing:
        existing = await manager.db.get_server_config(id)
    if not existing:
        raise HTTPException(404, f"Server '{id}' not found")

    # Check if server is running
    if id in manager.processes:
        process = manager.processes[id]
        if process.poll() is None:
            raise HTTPException(400, "Cannot update running server. Stop it first.")

    # Validate required fields
    if "name" not in config:
        raise HTTPException(400, "Server name is required")

    # Validate configuration for security
    validate_server_config(config)

    # Update config (preserve id)
    config["id"] = id

    # Save updated config (both database and in-memory)
    try:
        success = await manager.db.save_server_config(config)
        if not success:
            logger.warning(f"Database save failed for '{config['name']}', storing in-memory only")
    except DuplicateKeyError:
        # This shouldn't happen in update, but handle it anyway
        logger.error(f"Unexpected duplicate key error when updating server '{id}'")
        # Continue with in-memory update

    # Always update in-memory
    manager.configs[id] = config

    logger.info(f"Updated server configuration: {config['name']} (id: {id})")
    return {
        "message": f"Server '{id}' updated successfully",
        "config": config
    }


@router.delete("/servers/{id}")
async def delete_server(
    request: Request,
    id: str,
    token: str = Depends(get_token),
    user_id: str = Depends(get_current_user)
):
    """
    Soft delete server configuration (preserves data, stops server if running).

    Authorization: Only admins can delete server configurations.
    Regular users cannot delete servers (they can only stop instances they started).

    Args:
        id: Server identifier
        user_id: Current user (from token)

    Returns:
        Success message with deletion timestamp
    """
    manager = get_server_manager(request)

    # Check if server exists (in-memory or database)
    config = manager.configs.get(id)
    if not config:
        config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    # Check if server is already deleted
    if config.get("deleted_at"):
        raise HTTPException(410, f"Server '{id}' is already deleted")

    # Authorization: Temporarily allow all users to delete servers
    # TODO: Implement proper role-based access control (RBAC) with admin roles
    # when JWT authentication with role claims is added. For now, we allow
    # everyone to delete as requested (will add proper user/admin roles later).
    # Uncomment the check below when RBAC is ready:
    # if user_id != "admin":
    #     raise HTTPException(
    #         403,
    #         "Server deletion requires administrator privileges"
    #     )

    # Stop server if running
    if id in manager.processes:
        logger.info(f"Stopping server '{id}' before soft deletion...")
        await manager.stop_server(id)

    # Soft delete from database (sets deleted_at + enabled=false)
    success = await manager.db.soft_delete_server_config(id)
    if not success:
        raise HTTPException(500, f"Failed to delete server '{id}'")

    # Remove from in-memory cache
    if id in manager.configs:
        del manager.configs[id]

    from datetime import datetime
    deleted_at = datetime.utcnow().isoformat()
    logger.info(f"Soft deleted server configuration: {id}")
    return {
        "message": f"Server '{id}' deleted successfully",
        "deleted_at": deleted_at
    }


# ==================== Lifecycle Control ====================

@router.post("/servers/{id}/start")
async def start_server(
    request: Request,
    id: str,
    token: str = Depends(get_token),
    user_id: str = Depends(get_current_user)
):
    """
    Start an MCP server.

    Args:
        id: Server identifier
        user_id: User identifier (extracted from token)

    Returns:
        Success message with PID
    """
    manager = get_server_manager(request)

    # Check if server exists (in-memory or database)
    config = manager.configs.get(id)
    if not config:
        config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    # Check if server is enabled
    if not config.get("enabled", True):
        raise HTTPException(403, f"Cannot start server '{id}': Server is disabled")

    # Check if already running
    if id in manager.processes:
        process = manager.processes[id]
        if process.poll() is None:
            raise HTTPException(400, f"Server '{id}' is already running (PID: {process.pid})")

    # Start server with user tracking
    success = await manager.start_server(id, config, user_id=user_id)
    if not success:
        raise HTTPException(500, truncate_error(f"Failed to start server '{id}'"))

    # Get PID
    process = manager.processes.get(id)
    pid = process.pid if process else None

    logger.info(f"Started server '{id}' via API")
    return {
        "message": f"Server '{id}' started successfully",
        "pid": pid
    }


@router.post("/servers/{id}/stop")
async def stop_server(
    request: Request,
    id: str,
    force: bool = Query(False, description="Use SIGKILL instead of SIGTERM"),
    token: str = Depends(get_token),
    user_id: str = Depends(get_current_user)
):
    """
    Stop a running MCP server.

    Authorization: Users can only stop servers they started (unless admin).

    Args:
        id: Server identifier
        force: If true, use SIGKILL
        user_id: Current user (from token)

    Returns:
        Success message with exit code
    """
    manager = get_server_manager(request)

    # Check if server is running
    if id not in manager.processes:
        raise HTTPException(400, f"Server '{id}' is not running")

    # Authorization: Check if user started this server
    instance = await manager.db.get_instance_state(id)
    if instance:
        started_by = instance.get("started_by")
        # Allow if user started it, or if no owner (backward compatibility), or if anonymous mode
        if started_by and started_by != user_id and user_id != "anonymous":
            raise HTTPException(
                403,
                f"Forbidden: Server '{id}' was started by another user. Only the user who started it can stop it."
            )

    # Stop server
    success = await manager.stop_server(id, force=force)
    if not success:
        raise HTTPException(500, truncate_error(f"Failed to stop server '{id}'"))

    logger.info(f"Stopped server '{id}' via API (force={force})")
    return {
        "message": f"Server '{id}' stopped successfully",
        "forced": force
    }


@router.post("/servers/{id}/restart")
async def restart_server(
    request: Request,
    id: str,
    token: str = Depends(get_token),
    user_id: str = Depends(get_current_user)
):
    """
    Restart an MCP server.

    Authorization: Users can only restart servers they started (unless admin).

    Args:
        id: Server identifier
        user_id: Current user (from token)

    Returns:
        Success message with new PID
    """
    manager = get_server_manager(request)

    # Check if server exists (in-memory or database)
    config = manager.configs.get(id)
    if not config:
        config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    # Authorization: Check if user started this server
    instance = await manager.db.get_instance_state(id)
    if instance:
        started_by = instance.get("started_by")
        # Allow if user started it, or if no owner (backward compatibility), or if anonymous mode
        if started_by and started_by != user_id and user_id != "anonymous":
            raise HTTPException(
                403,
                f"Forbidden: Server '{id}' was started by another user. Only the user who started it can restart it."
            )

    # Restart server
    success = await manager.restart_server(id)
    if not success:
        raise HTTPException(500, truncate_error(f"Failed to restart server '{id}'"))

    # Get new PID
    process = manager.processes.get(id)
    pid = process.pid if process else None

    logger.info(f"Restarted server '{id}' via API")
    return {
        "message": f"Server '{id}' restarted successfully",
        "pid": pid
    }


@router.post("/servers/start-all")
async def start_all_servers(request: Request, token: str = Depends(get_token)):
    """
    Start all configured servers.

    Returns:
        Summary of started servers
    """
    manager = get_server_manager(request)

    configs = await manager.db.list_server_configs()
    started = []
    failed = []

    for config in configs:
        server_id = config.get("id")
        if not server_id:
            continue

        name = config.get("name", server_id)

        # Skip if already running
        if server_id in manager.processes:
            process = manager.processes[server_id]
            if process.poll() is None:
                continue

        # Start server
        success = await manager.start_server(server_id, config)
        if success:
            started.append(name)
        else:
            failed.append(name)

    logger.info(f"Started {len(started)} servers via API")
    return {
        "message": f"Started {len(started)} server(s)",
        "started": started,
        "failed": failed
    }


@router.post("/servers/stop-all")
async def stop_all_servers(request: Request, token: str = Depends(get_token)):
    """
    Stop all running servers.

    Returns:
        Summary of stopped servers
    """
    manager = get_server_manager(request)

    await manager.stop_all_servers()

    logger.info("Stopped all servers via API")
    return {
        "message": "All servers stopped successfully"
    }


# ==================== Status & Information ====================

@router.get("/servers/{id}/status")
async def get_server_status(request: Request, id: str):
    """
    Get detailed status of a server.

    Args:
        id: Server identifier

    Returns:
        Status information (state, pid, uptime, etc.)
    """
    manager = get_server_manager(request)

    status = await manager.get_server_status(id)

    if status["state"] == "not_found":
        raise HTTPException(404, f"Server '{id}' not found")

    return status


@router.get("/servers/{id}/logs")
async def get_server_logs(
    request: Request,
    id: str,
    lines: int = Query(100, description="Number of recent log lines")
):
    """
    Get recent logs for a server.

    Args:
        id: Server identifier
        lines: Number of recent lines to retrieve

    Returns:
        List of log entries
    """
    manager = get_server_manager(request)

    # Check if server exists (in-memory or database)
    config = manager.configs.get(id)
    if not config:
        config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    # Get logs from database
    logs = await manager.db.get_logs(id, lines=lines)

    return {
        "server": id,
        "logs": logs,
        "count": len(logs)
    }


# ==================== Environment Variable Management ====================

@router.get("/servers/{id}/instance/env")
async def get_server_instance_env(request: Request, id: str):
    """
    Get environment variable metadata for a server instance.

    Returns metadata about each environment variable:
    - present: Whether it has a value in the instance
    - required: Whether it's required for server operation
    - masked: Masked value if present (e.g., "****")
    - description: Help text for the user

    Args:
        id: Server identifier

    Returns:
        Dict of env var names to metadata
    """
    manager = get_server_manager(request)

    # Get server config to determine required env vars
    config = manager.configs.get(id)
    if not config:
        config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    # Get instance env (actual values set by user)
    instance_env = await manager.db.get_instance_env(id) or {}

    # Get config env (default/required env vars from config)
    config_env = config.get("env", {})

    # Build metadata response
    metadata = {}

    # Add all config env vars (these are the ones we expect)
    for key in config_env.keys():
        # Check if key exists in instance env with a non-empty, non-placeholder value
        value = instance_env.get(key, "")
        has_value = bool(value and value.strip() and not is_placeholder(value))
        metadata[key] = {
            "present": has_value,
            "required": True,  # All env vars in config are considered required
            "masked": "****" if has_value else None,
            "description": f"Environment variable for {config.get('name', id)}"
        }

    # Add any instance env vars not in config (user-added)
    for key, value in instance_env.items():
        if key not in metadata:
            has_value = bool(value and value.strip() and not is_placeholder(value))
            metadata[key] = {
                "present": has_value,
                "required": False,
                "masked": "****" if has_value else None,
                "description": "Custom environment variable"
            }

    return metadata


@router.put("/servers/{id}/instance/env")
async def update_server_instance_env(
    request: Request,
    id: str,
    env: Dict[str, str] = Body(...),
    token: str = Depends(get_token)
):
    """
    Update environment variables for a server instance.

    This updates the instance-specific env vars (user's API keys, etc.)
    without modifying the server config template.

    Args:
        id: Server identifier
        env: Dict of environment variable key-value pairs

    Returns:
        Success message with update status
    """
    manager = get_server_manager(request)

    # Check if server exists
    config = manager.configs.get(id)
    if not config:
        config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    # Validate env vars (comprehensive security validation)
    if not isinstance(env, dict):
        raise HTTPException(400, "Environment variables must be a dictionary")

    # Comprehensive validation for security and DoS prevention
    validate_env_variables(env)

    # Filter out placeholder values before saving
    # This prevents saving config defaults like "YOUR_API_KEY_HERE"
    # Only save non-placeholder, non-empty values
    filtered_env = {
        k: v for k, v in env.items()
        if v and v.strip() and not is_placeholder(v)
    }

    if not filtered_env:
        raise HTTPException(400, "No valid environment variables provided (all values were empty or placeholders)")

    # Save current env for rollback if restart fails
    old_env = None
    server_was_running = False
    if id in manager.processes:
        process = manager.processes[id]
        if process.poll() is None:  # Still running
            server_was_running = True
            # Get current env before update for potential rollback
            old_env = await manager.db.get_instance_env(id)

    # Update instance env in database (upserts if instance doesn't exist)
    success = await manager.db.update_instance_env(id, filtered_env)

    if not success:
        raise HTTPException(500, "Failed to update environment variables")

    logger.info(f"Updated instance env for server '{id}'")

    # If server is running, restart it to apply new env vars
    if server_was_running:
        logger.info(f"Restarting server '{id}' to apply new environment variables")
        restart_success = await manager.restart_server(id)
        if not restart_success:
            # Rollback env changes on restart failure
            if old_env is not None:
                logger.warning(f"Restart failed, rolling back env changes for server '{id}'")
                try:
                    # Rollback to old env
                    await manager.db.update_instance_env(id, old_env)
                    raise HTTPException(500, truncate_error(f"Failed to restart server '{id}' after updating env. Changes have been rolled back."))
                except Exception as rollback_error:
                    logger.critical(f"CRITICAL: Rollback failed for server '{id}': {rollback_error}")
                    raise HTTPException(500, truncate_error(f"Failed to restart server '{id}' and rollback also failed. Manual intervention required."))
            raise HTTPException(500, truncate_error(f"Failed to restart server '{id}' after updating env."))

    return {
        "message": f"Environment variables updated for server '{id}'",
        "env_updated": True
    }


@router.delete("/servers/{id}/instance/env")
async def delete_server_instance_env(
    request: Request,
    id: str,
    token: str = Depends(get_token)
):
    """
    Delete all environment variables from a server instance.

    This clears user-configured env vars, useful for testing or resetting.
    Does not affect the server_config template.

    Args:
        id: Server identifier

    Returns:
        Success message
    """
    manager = get_server_manager(request)

    # Check if server exists
    config = manager.configs.get(id)
    if not config:
        config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    # Clear instance env by deleting the env field from the instance
    try:
        result = await manager.db.db.fluidmcp_server_instances.update_one(
            {"server_id": id},
            {"$unset": {"env": ""}}
        )
        if result.matched_count == 0:
            logger.warning(f"No instance found for server '{id}', nothing to clear")
    except Exception as e:
        logger.error(f"Error clearing instance env: {e}")
        raise HTTPException(500, "Failed to clear environment variables")

    logger.info(f"Cleared instance env for server '{id}'")
    return {
        "message": f"Environment variables cleared for server '{id}'",
        "env_cleared": True
    }


# ==================== Tool Discovery & Execution (PDF Spec) ====================

@router.get("/servers/{id}/tools")
async def get_server_tools(request: Request, id: str):
    """
    Get discovered tools for a server.

    Tools are automatically discovered when the server starts and cached in MongoDB.
    Returns the cached tool list from the database.

    Args:
        id: Server identifier

    Returns:
        List of discovered tools with their schemas
    """
    manager = get_server_manager(request)

    # Get config with cached tools (database layer flattens it but tools field passes through)
    config = await manager.db.get_server_config(id)
    if not config:
        raise HTTPException(404, f"Server '{id}' not found")

    tools = config.get("tools", [])

    return {
        "server_id": id,
        "tools": tools,
        "count": len(tools)
    }


@router.post("/servers/{id}/tools/{tool_name}/run")
async def run_tool(
    request: Request,
    id: str,
    tool_name: str,
    arguments: Dict[str, Any] = Body(default={}),
    token: str = Depends(get_token)
):
    """
    Execute a tool on a running MCP server.

    Sends a tools/call JSON-RPC request to the running server process
    and returns the result.

    Args:
        id: Server identifier
        tool_name: Name of the tool to execute
        arguments: Tool arguments as dict

    Returns:
        Tool execution result
    """
    manager = get_server_manager(request)

    # Check if server is running
    if id not in manager.processes:
        raise HTTPException(400, f"Server '{id}' is not running")

    process = manager.processes[id]
    if process.poll() is not None:
        raise HTTPException(400, f"Server '{id}' has stopped")

    # Send tools/call request
    try:
        import json

        tool_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        logger.info(f"Executing tool '{tool_name}' on server '{id}'")
        process.stdin.write(json.dumps(tool_request) + "\n")
        process.stdin.flush()

        # Read response with 30 second timeout
        response_line = await asyncio.wait_for(
            asyncio.to_thread(process.stdout.readline),
            timeout=30.0
        )

        response = json.loads(response_line.strip())

        if "error" in response:
            raise HTTPException(500, truncate_error(f"Tool execution error: {response['error']}"))

        logger.info(f"Tool '{tool_name}' executed successfully on server '{id}'")
        return response.get("result", {})

    except asyncio.TimeoutError:
        raise HTTPException(504, "Tool execution timeout (>30s)")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse tool response for '{tool_name}' on '{id}': {e}")
        raise HTTPException(500, "Failed to parse tool response")
    except Exception as e:
        logger.exception(f"Tool execution failed for '{tool_name}' on '{id}': {e}")
        raise HTTPException(500, "Tool execution failed")


# ==================== LLM Management ====================

def get_llm_processes():
    """Get LLM processes from run_servers module."""
    # Import here to avoid circular dependency
    from ..services import get_llm_processes as _get_llm_processes
    return _get_llm_processes()


@router.get("/llm/models")
async def list_llm_models(
    token: str = Depends(get_token)
):
    """
    List all configured LLM models with their status.

    Returns:
        List of LLM models with status information
    """
    from ..services.replicate_client import _replicate_clients
    from ..services.llm_provider_registry import _registry_lock

    llm_processes = get_llm_processes()

    models = []

    # Add vLLM/Ollama/LM Studio models (process-based)
    for model_id, process in llm_processes.items():
        is_healthy, health_msg = await process.check_health()
        models.append({
            "id": model_id,
            "type": "process",  # vLLM, Ollama, etc.
            "is_running": process.is_running(),
            "is_healthy": is_healthy,
            "health_message": health_msg,
            "restart_policy": process.restart_policy,
            "restart_count": process.restart_count,
            "max_restarts": process.max_restarts,
            "consecutive_health_failures": process.consecutive_health_failures,
            "uptime_seconds": process.get_uptime(),
            "last_restart_time": process.last_restart_time,
            "last_health_check_time": process.last_health_check_time
        })

    # Add Replicate models (cloud-based)
    # CRITICAL: Copy items list under lock, then iterate outside lock to avoid holding lock during I/O
    with _registry_lock:
        replicate_items = list(_replicate_clients.items())

    for model_id, client in replicate_items:
        # Replicate clients don't have process lifecycle
        models.append({
            "id": model_id,
            "type": "replicate",
            "is_running": True,  # Always "running" (cloud-based)
            "is_healthy": True,  # Assume healthy (validated on registration)
            "health_message": "Cloud-based model (Replicate)",
            "model": client.model_name,
            "endpoint": "https://api.replicate.com"
        })

    return {
        "models": models,
        "total": len(models)
    }


@router.get("/llm/models/{model_id}")
async def get_llm_model_status(
    model_id: str,
    token: str = Depends(get_token)
):
    """
    Get detailed status for a specific LLM model.

    Args:
        model_id: Model identifier

    Returns:
        Detailed model status
    """
    from ..services.replicate_client import _replicate_clients
    from ..services.llm_provider_registry import _registry_lock

    llm_processes = get_llm_processes()

    # Check process-based models (vLLM, Ollama, etc.)
    if model_id in llm_processes:
        process = llm_processes[model_id]
        is_healthy, health_msg = await process.check_health()

        return {
            "id": model_id,
            "type": "process",
            "is_running": process.is_running(),
            "is_healthy": is_healthy,
            "health_message": health_msg,
            "restart_policy": process.restart_policy,
            "restart_count": process.restart_count,
            "max_restarts": process.max_restarts,
            "consecutive_health_failures": process.consecutive_health_failures,
            "uptime_seconds": process.get_uptime(),
            "last_restart_time": process.last_restart_time,
            "last_health_check_time": process.last_health_check_time,
            # Issue #3 fix: Use asyncio.to_thread to avoid blocking event loop with file I/O
            "has_cuda_oom": await asyncio.to_thread(process.check_for_cuda_oom)
        }

    # Check cloud-based models (Replicate)
    with _registry_lock:
        if model_id in _replicate_clients:
            client = _replicate_clients[model_id]
            return {
                "id": model_id,
                "type": "replicate",
                "is_running": True,  # Always "running" (cloud-based)
                "is_healthy": True,  # Assume healthy (validated on registration)
                "health_message": "Cloud-based model (Replicate)",
                "model": client.model_name,
                "endpoint": "https://api.replicate.com",
                "timeout": client.timeout,
                "max_retries": client.max_retries
            }

    # Model not found in either registry
    raise HTTPException(404, f"LLM model '{model_id}' not found")


@router.post("/llm/models/{model_id}/restart")
async def restart_llm_model(
    request: Request,
    model_id: str,
    token: str = Depends(get_token)
):
    """
    Manually restart a specific LLM model.

    Args:
        model_id: Model identifier

    Returns:
        Restart result
    """
    llm_processes = get_llm_processes()

    if model_id not in llm_processes:
        raise HTTPException(404, f"LLM model '{model_id}' not found")

    process = llm_processes[model_id]

    # Check if restart is allowed
    if not process.can_restart():
        raise HTTPException(
            400,
            f"Cannot restart model '{model_id}': restart policy is '{process.restart_policy}' "
            f"or max restarts ({process.max_restarts}) reached"
        )

    logger.info(f"Manual restart requested for LLM model '{model_id}'")

    # Attempt restart
    success = await process.attempt_restart()

    if success:
        return {
            "message": f"LLM model '{model_id}' restarted successfully",
            "restart_count": process.restart_count,
            "uptime_seconds": process.get_uptime()
        }
    else:
        raise HTTPException(
            500,
            f"Failed to restart LLM model '{model_id}'. Check logs for details."
        )


@router.post("/llm/models/{model_id}/stop")
async def stop_llm_model(
    request: Request,
    model_id: str,
    force: bool = Query(False, description="Force kill the process"),
    token: str = Depends(get_token)
):
    """
    Stop a specific LLM model and persist state to database.

    Args:
        model_id: Model identifier
        force: If true, force kill the process (SIGKILL)

    Returns:
        Stop result with persisted state
    """
    llm_processes = get_llm_processes()

    if model_id not in llm_processes:
        raise HTTPException(404, f"LLM model '{model_id}' not found")

    process = llm_processes[model_id]

    if not process.is_running():
        return {"message": f"LLM model '{model_id}' is already stopped", "status": "stopped"}

    logger.info(f"Stop requested for LLM model '{model_id}' (force={force})")

    try:
        # Stop the process
        if force:
            process.force_kill()
            stop_method = "force_killed"
        else:
            process.stop()
            stop_method = "graceful"

        # Update state in persistence backend
        db = get_db_manager()
        if db and hasattr(db, 'update_llm_model'):
            try:
                from datetime import datetime
                await db.update_llm_model(model_id, {
                    "state": "stopped",
                    "stopped_at": datetime.utcnow().isoformat(),
                    "stop_method": stop_method
                })
                state_persisted = True
            except Exception as e:
                logger.warning(f"Failed to persist stopped state for '{model_id}': {e}")
                state_persisted = False
        else:
            state_persisted = False

        return {
            "message": f"LLM model '{model_id}' stopped ({stop_method})",
            "status": "stopped",
            "persisted": state_persisted
        }
    except Exception as e:
        logger.error(f"Error stopping LLM model '{model_id}': {e}", exc_info=True)
        raise HTTPException(500, "Failed to stop LLM model")


@router.post("/llm/models/{model_id}/start")
async def start_llm_model(
    request: Request,
    model_id: str,
    token: str = Depends(get_token)
):
    """
    Start a previously stopped LLM model.

    Reads model configuration from database and launches the process.

    Args:
        model_id: Model identifier

    Returns:
        Start result with process status
    """
    from ..services.llm_launcher import launch_single_llm_model
    from ..services.run_servers import get_llm_processes, register_llm_process
    from ..services.llm_provider_registry import _registry_lock, _llm_models_config

    # Check if already running
    llm_processes = get_llm_processes()
    if model_id in llm_processes:
        process = llm_processes[model_id]
        if process.is_running():
            return {
                "message": f"LLM model '{model_id}' is already running",
                "status": "running"
            }

    # Get model config from database
    db = get_db_manager()
    if not db:
        raise HTTPException(500, "Database not available")

    try:
        model_doc = await db.get_llm_model(model_id)
        if not model_doc:
            raise HTTPException(404, f"Model '{model_id}' not found in database")

        model_type = model_doc.get("type")
        if model_type not in ("vllm", "ollama", "lmstudio"):
            raise HTTPException(400, f"Model type '{model_type}' does not support start operation")

        # Extract config
        mongo_internal_fields = ["created_at", "updated_at", "_id", "model_id", "type", "state", "stopped_at", "started_at", "stop_method"]
        model_config = {
            k: v
            for k, v in model_doc.items()
            if k not in mongo_internal_fields
        }

        # Launch the process
        logger.info(f"Starting LLM model '{model_id}' (type: {model_type})")
        process = launch_single_llm_model(model_id, model_config)

        if not process:
            raise HTTPException(500, f"Failed to start model '{model_id}'")

        # Register in global registry (direct assignment to avoid nested locks)
        from ..services.run_servers import get_llm_processes
        with _registry_lock:
            _llm_processes = get_llm_processes()
            _llm_processes[model_id] = process
            _llm_models_config[model_id] = model_config

        # Update state in database
        state_persisted = False
        try:
            from datetime import datetime
            await db.update_llm_model(model_id, {
                "state": "running",
                "started_at": datetime.utcnow().isoformat(),
                "stopped_at": None,
                "stop_method": None
            })
            state_persisted = True
        except Exception as e:
            logger.warning(f"Failed to persist running state for '{model_id}': {e}")

        logger.info(f"Successfully started LLM model '{model_id}'")

        return {
            "message": f"LLM model '{model_id}' started successfully",
            "status": "running",
            "model_id": model_id,
            "type": model_type,
            "persisted": state_persisted
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting LLM model '{model_id}': {e}", exc_info=True)
        raise HTTPException(500, f"Failed to start model: {str(e)}")


@router.get("/llm/models/{model_id}/logs")
async def get_llm_model_logs(
    model_id: str,
    lines: int = Query(100, description="Number of recent lines to retrieve", ge=1, le=10000),
    token: str = Depends(get_token)
):
    """
    Get recent stderr logs for a specific LLM model.

    Args:
        model_id: Model identifier
        lines: Number of recent lines to retrieve (1-10000)

    Returns:
        Log lines
    """
    llm_processes = get_llm_processes()

    if model_id not in llm_processes:
        raise HTTPException(404, f"LLM model '{model_id}' not found")

    process = llm_processes[model_id]
    log_path = process.get_stderr_log_path()

    if not os.path.exists(log_path):
        return {
            "model_id": model_id,
            "log_path": log_path,
            "lines": [],
            "message": "Log file does not exist yet"
        }

    try:
        # Efficiently read only the last N lines using backwards seeking
        # This avoids loading large log files entirely into memory
        # TODO: For very large files (>100MB), consider mmap for better performance
        block_size = 8192
        buffer = b""
        newline_count = 0

        with open(log_path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            position = file_size

            # Read backwards until we have enough lines or reach start of file
            while position > 0 and newline_count <= lines:
                read_size = block_size if position >= block_size else position
                position -= read_size
                f.seek(position)
                data = f.read(read_size)
                buffer = data + buffer
                newline_count = buffer.count(b"\n")

        # Decode and split into lines
        text = buffer.decode("utf-8", errors="ignore")
        all_lines_read = text.splitlines(keepends=True)
        recent_lines = all_lines_read[-lines:] if len(all_lines_read) > lines else all_lines_read

        # Note: total_lines is approximate when file is larger than what we read
        total_lines_approx = len(all_lines_read)

        return {
            "model_id": model_id,
            "lines": recent_lines,
            "total_lines": total_lines_approx,
            "returned_lines": len(recent_lines)
        }
    except Exception as e:
        logger.error(f"Error reading logs for '{model_id}': {e}", exc_info=True)
        raise HTTPException(500, "Failed to read logs")


@router.post("/llm/models/{model_id}/health-check")
async def trigger_health_check(
    request: Request,
    model_id: str,
    token: str = Depends(get_token)
):
    """
    Manually trigger a health check for a specific LLM model.

    Args:
        model_id: Model identifier

    Returns:
        Health check result
    """
    llm_processes = get_llm_processes()

    if model_id not in llm_processes:
        raise HTTPException(404, f"LLM model '{model_id}' not found")

    process = llm_processes[model_id]

    logger.info(f"Manual health check triggered for LLM model '{model_id}'")

    is_healthy, error_msg = await process.check_health()

    return {
        "model_id": model_id,
        "is_healthy": is_healthy,
        "health_message": error_msg,
        "consecutive_health_failures": process.consecutive_health_failures,
        "last_health_check_time": process.last_health_check_time,
        # Issue #3 fix: Use asyncio.to_thread to avoid blocking event loop with file I/O
        "has_cuda_oom": await asyncio.to_thread(process.check_for_cuda_oom)
    }


# ============================================================================
# Unified LLM Inference Endpoints (Provider-Agnostic OpenAI-Compatible)
# ============================================================================

@router.post("/llm/v1/chat/completions")
async def unified_chat_completions(
    request: Request,
    request_body: Dict[str, Any] = Body(...),
    token: str = Depends(get_token)
):
    """
    OpenAI-compatible chat completions endpoint (works for ALL provider types).

    Supports vLLM, Replicate, Ollama, and future providers.
    Provider type is determined from config, not from the route.

    Args:
        request: FastAPI Request object for rate limiting
        request_body: OpenAI-format chat request with model, messages, temperature, etc.

    Returns:
        OpenAI-format chat completion response

    Example request:
        {
          "model": "llama-2-70b",
          "messages": [{"role": "user", "content": "Hello"}],
          "temperature": 0.7,
          "max_tokens": 100
        }
    """
    # CRITICAL FIX: Add rate limiting to prevent DDoS attacks
    client_ip = get_client_ip(request)
    rate_limit_key = get_rate_limit_key("chat_completions", token or "anonymous", client_ip)
    max_requests, window_seconds = RATE_LIMIT_CHAT_COMPLETIONS
    check_rate_limit(rate_limit_key, max_requests=max_requests, window_seconds=window_seconds)

    # Extract model_id from request body (OpenAI-style)
    model_id = request_body.get("model")
    if not model_id:
        raise HTTPException(400, "Missing required field 'model' in request body")

    # Get provider type from registry
    provider_type = get_model_type(model_id)
    if not provider_type:
        raise HTTPException(404, f"Model '{model_id}' not found in configuration")

    logger.info(f"Chat completion request for model '{model_id}' (type: {provider_type})")

    # Initialize metrics collector (record start after config validation)
    collector = get_metrics_collector()

    # Route to appropriate provider handler
    if provider_type == "replicate":
        # Use Replicate adapter (converts OpenAI → Replicate → OpenAI)
        # The adapter already converts httpx errors to HTTPException, no need to catch them here
        # Record request start after config validation
        start_time = collector.record_request_start(model_id, provider_type)

        try:
            timeout = request_body.get("timeout", 300)
            response = await replicate_chat_completion(model_id, request_body, timeout)

            # Record successful request with token usage
            usage = response.get("usage", {})
            collector.record_request_success(
                model_id=model_id,
                start_time=start_time,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0)
            )

            return response
        except HTTPException as e:
            # Record failed request
            collector.record_request_failure(
                model_id=model_id,
                start_time=start_time,
                status_code=e.status_code
            )
            raise
        except Exception as e:
            # Record unexpected error and log details
            collector.record_request_failure(
                model_id=model_id,
                start_time=start_time,
                status_code=500
            )
            logger.exception(f"Unexpected error in chat completions for model '{model_id}': {e}")
            raise HTTPException(500, truncate_error(f"Internal server error while processing request for model '{model_id}'"))

    elif provider_type in ("vllm", "ollama", "lmstudio"):
        # Proxy to OpenAI-compatible endpoint (vLLM, Ollama, LM Studio all use same format)
        # Validate config first (before metrics tracking)
        model_config = get_model_config(model_id)
        if not model_config:
            raise HTTPException(500, truncate_error(f"Model '{model_id}' config not found"))

        base_url = model_config.get("endpoints", {}).get("base_url")

        if not base_url:
            raise HTTPException(500, truncate_error(f"{provider_type} model '{model_id}' missing base_url in config"))

        # Record request start (after config validation, before any processing)
        start_time = collector.record_request_start(model_id, provider_type)

        # Check if streaming is requested
        is_streaming = request_body.get("stream", False)

        if is_streaming:
            # Return streaming response using shared client
            http_client = _get_http_client()

            async def stream_generator():
                try:
                    async with http_client.stream(
                        "POST",
                        f"{base_url}/chat/completions",
                        json=request_body
                    ) as response:
                        response.raise_for_status()

                        async for chunk in response.aiter_bytes():
                            yield chunk

                        # Record successful streaming request after stream completes
                        # Note: Token usage not available for streaming responses
                        collector.record_request_success(
                            model_id=model_id,
                            start_time=start_time,
                            prompt_tokens=0,
                            completion_tokens=0
                        )
                except httpx.HTTPStatusError as e:
                    # Read error body with size limit to avoid buffering entire response
                    try:
                        # Read at most MAX_ERROR_MESSAGE_LENGTH bytes from response
                        error_bytes = await e.response.aread()
                        error_text = error_bytes[:MAX_ERROR_MESSAGE_LENGTH].decode('utf-8', errors='replace')
                        if len(error_bytes) > MAX_ERROR_MESSAGE_LENGTH:
                            error_text += "... [truncated]"
                    except Exception:
                        error_text = str(e)

                    logger.error(f"{provider_type} streaming error {e.response.status_code}: {error_text}")

                    # Record failed streaming request
                    collector.record_request_failure(
                        model_id=model_id,
                        start_time=start_time,
                        status_code=e.response.status_code
                    )

                    # Emit SSE error event with proper JSON escaping
                    error_payload = json.dumps({"error": f"{provider_type} error: {error_text}", "status": e.response.status_code})
                    yield f"event: error\ndata: {error_payload}\n\n".encode()
                except httpx.RequestError as e:
                    logger.error(f"{provider_type} streaming connection error: {e}")

                    # Record connection error
                    collector.record_request_failure(
                        model_id=model_id,
                        start_time=start_time,
                        status_code=502
                    )

                    # Emit SSE error event with proper JSON escaping
                    error_payload = json.dumps({"error": f"Failed to connect to {provider_type} server: {str(e)}"})
                    yield f"event: error\ndata: {error_payload}\n\n".encode()

            return StreamingResponse(
                stream_generator(),
                media_type="text/event-stream"
            )

        # Non-streaming request using shared client
        try:
            http_client = _get_http_client()
            response = await http_client.post(
                f"{base_url}/chat/completions",
                json=request_body
            )
            response.raise_for_status()
            response_json = response.json()

            # Record successful request with token usage
            usage = response_json.get("usage", {})
            collector.record_request_success(
                model_id=model_id,
                start_time=start_time,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0)
            )

            return response_json
        except httpx.HTTPStatusError as e:
            # Read error body with size limit to avoid buffering entire response
            try:
                error_bytes = await e.response.aread()
                error_text = error_bytes[:MAX_ERROR_MESSAGE_LENGTH].decode('utf-8', errors='replace')
                if len(error_bytes) > MAX_ERROR_MESSAGE_LENGTH:
                    error_text += "... [truncated]"
            except Exception:
                error_text = str(e)

            logger.error(f"{provider_type} returned error {e.response.status_code}: {error_text}")

            # Record failed request
            collector.record_request_failure(
                model_id=model_id,
                start_time=start_time,
                status_code=e.response.status_code
            )

            raise HTTPException(e.response.status_code, f"{provider_type} error: {error_text}")
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to {provider_type}: {e}")

            # Record connection error
            collector.record_request_failure(
                model_id=model_id,
                start_time=start_time,
                status_code=502
            )

            raise HTTPException(502, truncate_error(f"Failed to connect to {provider_type} server: {str(e)}"))

    else:
        raise HTTPException(501, truncate_error(f"Provider type '{provider_type}' not yet supported for chat completions"))


@router.post("/llm/v1/completions")
async def unified_completions(
    request: Request,
    request_body: Dict[str, Any] = Body(...),
    token: str = Depends(get_token)
):
    """
    OpenAI-compatible text completions endpoint (currently supports provider types: vllm, ollama, lmstudio).

    Args:
        request: FastAPI Request object for rate limiting
        request_body: OpenAI-format completion request with model and prompt

    Returns:
        OpenAI-format completion response

    Example request:
        {
          "model": "llama-2-70b",
          "prompt": "Once upon a time",
          "max_tokens": 100
        }
    """
    # CRITICAL FIX: Add rate limiting to prevent DDoS attacks
    client_ip = get_client_ip(request)
    rate_limit_key = get_rate_limit_key("completions", token or "anonymous", client_ip)
    max_requests, window_seconds = RATE_LIMIT_COMPLETIONS
    check_rate_limit(rate_limit_key, max_requests=max_requests, window_seconds=window_seconds)

    # Extract model_id from request body (OpenAI-style)
    model_id = request_body.get("model")
    if not model_id:
        raise HTTPException(400, "Missing required field 'model' in request body")

    provider_type = get_model_type(model_id)
    if not provider_type:
        raise HTTPException(404, f"Model '{model_id}' not found in configuration")

    # Initialize metrics collector (record start after config validation)
    collector = get_metrics_collector()

    if provider_type in ("vllm", "ollama", "lmstudio"):
        # Proxy to OpenAI-compatible completions endpoint (vLLM, Ollama, LM Studio)
        model_config = get_model_config(model_id)
        if not model_config:
            raise HTTPException(500, truncate_error(f"Model '{model_id}' config not found"))

        base_url = model_config.get("endpoints", {}).get("base_url")

        if not base_url:
            raise HTTPException(500, truncate_error(f"{provider_type} model '{model_id}' missing base_url in config"))

        # Record request start after config validation
        start_time = collector.record_request_start(model_id, provider_type)

        # Check if streaming is requested
        is_streaming = request_body.get("stream", False)

        if is_streaming:
            # Return streaming response using shared client
            http_client = _get_http_client()

            async def stream_generator():
                try:
                    async with http_client.stream(
                        "POST",
                        f"{base_url}/completions",
                        json=request_body
                    ) as response:
                        response.raise_for_status()

                        async for chunk in response.aiter_bytes():
                            yield chunk

                        # Record successful streaming request after stream completes
                        # Note: Token usage not available for streaming responses
                        collector.record_request_success(
                            model_id=model_id,
                            start_time=start_time,
                            prompt_tokens=0,
                            completion_tokens=0
                        )
                except httpx.HTTPStatusError as e:
                    # Read error body with size limit to avoid buffering entire response
                    try:
                        # Read at most MAX_ERROR_MESSAGE_LENGTH bytes from response
                        error_bytes = await e.response.aread()
                        error_text = error_bytes[:MAX_ERROR_MESSAGE_LENGTH].decode('utf-8', errors='replace')
                        if len(error_bytes) > MAX_ERROR_MESSAGE_LENGTH:
                            error_text += "... [truncated]"
                    except Exception:
                        error_text = str(e)

                    logger.error(f"{provider_type} streaming error {e.response.status_code}: {error_text}")

                    # Record failed streaming request
                    collector.record_request_failure(
                        model_id=model_id,
                        start_time=start_time,
                        status_code=e.response.status_code
                    )

                    # Emit SSE error event with proper JSON escaping
                    error_payload = json.dumps({"error": f"{provider_type} error: {error_text}", "status": e.response.status_code})
                    yield f"event: error\ndata: {error_payload}\n\n".encode()
                except httpx.RequestError as e:
                    logger.error(f"{provider_type} streaming connection error: {e}")

                    # Record connection error
                    collector.record_request_failure(
                        model_id=model_id,
                        start_time=start_time,
                        status_code=502
                    )

                    # Emit SSE error event with proper JSON escaping
                    error_payload = json.dumps({"error": f"Failed to connect to {provider_type} server: {str(e)}"})
                    yield f"event: error\ndata: {error_payload}\n\n".encode()

            return StreamingResponse(
                stream_generator(),
                media_type="text/event-stream"
            )

        # Non-streaming request using shared client
        try:
            http_client = _get_http_client()
            response = await http_client.post(
                f"{base_url}/completions",
                json=request_body
            )
            response.raise_for_status()
            response_json = response.json()

            # Record successful request with token usage
            usage = response_json.get("usage", {})
            collector.record_request_success(
                model_id=model_id,
                start_time=start_time,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0)
            )

            return response_json
        except httpx.HTTPStatusError as e:
            # Read error body with size limit to avoid buffering entire response
            try:
                error_bytes = await e.response.aread()
                error_text = error_bytes[:MAX_ERROR_MESSAGE_LENGTH].decode('utf-8', errors='replace')
                if len(error_bytes) > MAX_ERROR_MESSAGE_LENGTH:
                    error_text += "... [truncated]"
            except Exception:
                error_text = str(e)

            # Record failed request
            collector.record_request_failure(
                model_id=model_id,
                start_time=start_time,
                status_code=e.response.status_code
            )

            raise HTTPException(e.response.status_code, f"{provider_type} error: {error_text}")
        except httpx.RequestError as e:
            # Record connection error
            collector.record_request_failure(
                model_id=model_id,
                start_time=start_time,
                status_code=502
            )

            raise HTTPException(502, truncate_error(f"Failed to connect to {provider_type}: {str(e)}"))

    else:
        raise HTTPException(501, truncate_error(f"Provider type '{provider_type}' not yet supported for completions"))


@router.get("/llm/v1/models")
async def unified_list_models(
    request: Request,
    token: str = Depends(get_token),
    model: str = None
):
    """
    OpenAI-compatible models list endpoint.

    Lists all available models or returns details for a specific model.

    Args:
        request: FastAPI Request object for rate limiting
        model: Optional model ID to get details for specific model

    Returns:
        OpenAI-format model list or single model details
    """
    # CRITICAL FIX: Add rate limiting to prevent DDoS attacks
    client_ip = get_client_ip(request)
    rate_limit_key = get_rate_limit_key("models_list", token or "anonymous", client_ip)
    max_requests, window_seconds = RATE_LIMIT_MODELS_GET
    check_rate_limit(rate_limit_key, max_requests=max_requests, window_seconds=window_seconds)

    if model:
        # Return specific model details (single model object, not list)
        config = get_model_config(model)
        if not config:
            raise HTTPException(404, f"Model '{model}' not found")

        return {
            "id": model,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "fluidmcp",
            "permission": [],
            "root": model,
            "parent": None
        }
    else:
        # Return all models
        from ..services.llm_provider_registry import list_all_models
        models = list_all_models()

        created_timestamp = int(time.time())
        all_models = []
        for model_info in models:
            all_models.append({
                "id": model_info["id"],
                "object": "model",
                "created": created_timestamp,
                "owned_by": "fluidmcp",
                "permission": [],
                "root": model_info["id"],
                "parent": None
            })

        return {
            "object": "list",
            "data": all_models
        }


@router.get("/llm/v1/models/{model_id}")
async def unified_get_model(
    request: Request,
    model_id: str,
    token: str = Depends(get_token)
):
    """
    OpenAI-compatible retrieve model endpoint.

    Returns details for a specific model by ID.

    Args:
        request: FastAPI Request object for rate limiting
        model_id: The model ID to retrieve

    Returns:
        OpenAI-format model details

    Example:
        GET /api/llm/v1/models/llama-2-70b
        {
            "id": "llama-2-70b",
            "object": "model",
            "created": 1677649963,
            "owned_by": "fluidmcp"
        }
    """
    # CRITICAL FIX: Add rate limiting to prevent DDoS attacks
    client_ip = get_client_ip(request)
    rate_limit_key = get_rate_limit_key("models_get", token or "anonymous", client_ip)
    max_requests, window_seconds = RATE_LIMIT_MODELS_GET
    check_rate_limit(rate_limit_key, max_requests=max_requests, window_seconds=window_seconds)

    config = get_model_config(model_id)
    if not config:
        raise HTTPException(404, f"Model '{model_id}' not found")

    return {
        "id": model_id,
        "object": "model",
        "created": int(time.time()),
        "owned_by": "fluidmcp",
        "permission": [],
        "root": model_id,
        "parent": None
    }


# ============================================================================
# ============================================================================
# Metrics Endpoints (Observability)
# ============================================================================

@router.get("/metrics")
async def get_metrics_prometheus(
    token: str = Depends(get_token)
):
    """
    Get Prometheus-formatted metrics for all LLM models.

    Returns metrics including:
    - Request counts (total, successful, failed)
    - Latency statistics (avg, min, max)
    - Token usage (prompt, completion, total)
    - Error counts by status code
    - Uptime

    Example:
        curl http://localhost:8099/api/metrics
    """
    collector = get_metrics_collector()
    return Response(
        content=collector.export_prometheus(),
        media_type="text/plain; version=0.0.4"
    )


@router.get("/metrics/json")
async def get_metrics_json(
    token: str = Depends(get_token)
):
    """
    Get JSON-formatted metrics for all LLM models.

    Returns structured metrics data suitable for dashboards and monitoring tools.

    Example:
        curl http://localhost:8099/api/metrics/json
    """
    collector = get_metrics_collector()
    return collector.export_json()


@router.post("/metrics/reset")
async def reset_metrics(
    model_id: str = Query(None, description="Model ID to reset, or omit to reset all"),
    token: str = Depends(get_token)
):
    """
    Reset LLM metrics for a specific model or all models.

    Args:
        model_id: Optional model ID. If not provided, resets all metrics.

    Example:
        # Reset all metrics
        curl -X POST http://localhost:8099/api/metrics/reset

        # Reset specific model
        curl -X POST http://localhost:8099/api/metrics/reset?model_id=llama-2-70b
    """
    collector = get_metrics_collector()
    collector.reset_metrics(model_id)

    target = "all models" if not model_id else f"model '{model_id}'"
    return {
        "message": f"Metrics reset successfully for {target}"
    }


@router.get("/metrics/cache/stats")
async def get_cache_stats(token: str = Depends(get_token)):
    """
    Get response cache statistics.

    Returns cache performance metrics including:
    - Hit/miss counts
    - Hit rate percentage
    - Current cache size
    - TTL configuration

    Also updates the unified metrics registry for Prometheus scraping.

    Returns:
        Cache statistics dict
    """
    from ..services.response_cache import peek_response_cache
    from ..services.replicate_metrics import update_cache_metrics

    # Peek at existing cache without creating it
    cache = await peek_response_cache()
    if cache is None:
        # Update metrics (will set all to 0)
        await update_cache_metrics()
        return {
            "enabled": False,
            "message": "Cache is not initialized (no models with caching enabled have been used)"
        }

    stats = await cache.get_stats()

    # Update unified metrics registry
    await update_cache_metrics()

    return {
        "enabled": True,
        **stats
    }


@router.post("/metrics/cache/clear")
async def clear_cache(token: str = Depends(get_token)):
    """
    Clear all cached responses.

    Useful for testing or forcing fresh API calls.

    Returns:
        Number of entries cleared
    """
    from ..services.response_cache import clear_response_cache

    count = await clear_response_cache()
    logger.info(f"Cache cleared via API: {count} entries removed")
    return {"message": "Cache cleared successfully", "entries_cleared": count}


@router.get("/metrics/rate-limiters")
async def get_rate_limiter_stats(token: str = Depends(get_token)):
    """
    Get rate limiter statistics for all models.

    Returns available token counts for each model's rate limiter.

    Also updates the unified metrics registry for Prometheus scraping.

    Returns:
        Dict with rate_limiters (dict of model_id -> stats) and total_models count
    """
    from ..services.rate_limiter import get_all_rate_limiter_stats
    from ..services.replicate_metrics import update_rate_limiter_metrics

    stats = await get_all_rate_limiter_stats()

    # Update unified metrics registry
    await update_rate_limiter_metrics()

    return {
        "rate_limiters": stats,
        "total_models": len(stats)
    }


@router.get("/metrics/rate-limiters/{model_id}")
async def get_model_rate_limiter_stats(
    model_id: str,
    token: str = Depends(get_token)
):
    """
    Get rate limiter statistics for a specific model.

    Args:
        model_id: Model identifier

    Returns:
        Rate limiter stats including available tokens, capacity, and utilization

    Raises:
        HTTPException(404): If no rate limiter exists for the model
    """
    from ..services.rate_limiter import get_all_rate_limiter_stats

    # Use get_all to avoid creating limiters as side effect
    stats = await get_all_rate_limiter_stats()
    model_stats = stats.get(model_id)

    if model_stats is None:
        raise HTTPException(404, f"No rate limiter found for model '{model_id}'")

    return {
        "model_id": model_id,
        **model_stats
    }


@router.post("/metrics/rate-limiters/clear")
async def clear_rate_limiters(token: str = Depends(get_token)):
    """
    Clear all rate limiters (removes all registered limiters).

    Useful for testing or freeing memory in long-running processes.

    Returns:
        Number of limiters cleared
    """
    from ..services.rate_limiter import clear_rate_limiters as clear_limiters_func

    count = await clear_limiters_func()
    return {"message": "Rate limiters cleared successfully", "limiters_cleared": count}


@router.get("/metrics/models/{model_id}")
async def get_model_metrics(
    model_id: str,
    token: str = Depends(get_token)
):
    """
    Get detailed LLM metrics for a specific model.

    Args:
        model_id: Model identifier

    Returns:
        Detailed metrics including request counts, latency, tokens, and errors

    Example:
        curl http://localhost:8099/api/metrics/models/llama-2-70b
    """
    collector = get_metrics_collector()
    metrics = collector.get_model_metrics(model_id)

    if not metrics:
        raise HTTPException(404, f"No metrics found for model '{model_id}'")

    return {
        "model_id": model_id,
        "provider_type": metrics.provider_type,
        "requests": {
            "total": metrics.total_requests,
            "successful": metrics.successful_requests,
            "failed": metrics.failed_requests,
            "success_rate_percent": round(metrics.success_rate(), 2),
            "error_rate_percent": round(metrics.error_rate(), 2),
        },
        "latency": {
            "avg_seconds": round(metrics.avg_latency(), 3),
            "min_seconds": round(metrics.min_latency, 3) if metrics.min_latency != float('inf') else None,
            "max_seconds": round(metrics.max_latency, 3),
        },
        "tokens": {
            "prompt": metrics.total_prompt_tokens,
            "completion": metrics.total_completion_tokens,
            "total": metrics.total_tokens,
        },
        "errors_by_status": dict(metrics.errors_by_status),
    }


# ==================== LLM Model Registration ====================

@router.post("/llm/models")
async def register_llm_model(
    request: Request,
    config: ReplicateModelConfig,
    token: str = Depends(get_token)
):
    """
    Register a new LLM model dynamically.

    Rate limit: 10 requests per minute per client.

    Currently supports:
    - Replicate models (cloud inference)

    Request Body:
        model_id (str): Unique model identifier
        type (str): Model provider type ('replicate', 'vllm', 'ollama', etc.)
        model (str): Provider-specific model name
        api_key (str): API key (supports ${ENV_VAR} syntax)
        default_params (dict): Default inference parameters
        timeout (int): Request timeout in seconds
        max_retries (int): Maximum retry attempts

    Returns:
        Success message with model ID
    """
    from ..services.replicate_client import ReplicateClient, _replicate_clients
    from ..services.llm_provider_registry import _llm_models_config, _registry_lock

    # Apply rate limiting
    client_ip = get_client_ip(request)
    rate_limit_key = get_rate_limit_key("register_model", token, client_ip)
    max_requests, window_seconds = RATE_LIMIT_MODEL_REGISTRATION
    check_rate_limit(rate_limit_key, max_requests=max_requests, window_seconds=window_seconds)

    # Pydantic model handles all validation
    model_id = config.model_id
    model_type = config.type

    # Handle different model types
    if model_type == "replicate":
        # Initialize variables early so they're available in exception handlers
        db = None
        saved = False

        try:
            # Get database manager (may raise HTTPException)
            db = get_database_manager(request)
            # Convert Pydantic model to dict (remove model_id as it's passed separately)
            model_config = config.model_dump(exclude={"model_id"})

            # API key validation now handled by Pydantic field_validator

            # COPILOT COMMENT 6 FIX: Document TOCTOU limitation of early check
            # CRITICAL FIX: Check for collision BEFORE expensive operations (client init, health check)
            # This prevents wasted resources from duplicate registrations
            #
            # IMPORTANT: This is a best-effort early check with TOCTOU limitation:
            # - Another thread could register the same model_id between this check and the final check (line 2682)
            # - This is acceptable because:
            #   1. The final authoritative check (inside lock after persistence) prevents actual duplicates
            #   2. This early check only optimizes for the common case (duplicate request for already-registered model)
            #   3. Worst case: wasted client initialization + health check for a concurrent duplicate
            # - The lock is released immediately to allow concurrent registrations of different models
            with _registry_lock:
                if model_id in _replicate_clients:
                    raise HTTPException(400, f"Model '{model_id}' already registered as Replicate model")
                if model_id in _llm_models_config:
                    raise HTTPException(400, f"Model '{model_id}' already registered in provider registry")

            # Initialize Replicate client and perform health check (outside lock for concurrency)
            client = ReplicateClient(model_id, model_config)
            client_created = True  # Track if we need to clean up

            try:
                if not await client.health_check():
                    raise HTTPException(500, truncate_error(f"Health check failed for model '{model_id}'"))
            except Exception:
                # Clean up client on health check failure
                try:
                    await client.close()
                    client_created = False
                except Exception as e:
                    logger.debug(f"Failed to close client during cleanup: {e}")  # Best effort cleanup
                raise

            # Save to persistence backend (MongoDB or in-memory)
            # CRITICAL: Do this BEFORE registering in global registries to prevent race conditions
            try:
                try:
                    saved = await db.save_llm_model(config.model_dump())
                    if not saved:
                        # Persistence save failed - decide whether to fail based on environment
                        require_persistence = os.getenv("REQUIRE_MONGODB_PERSISTENCE", "false").lower() == "true"

                        if require_persistence:
                            raise HTTPException(500, "Persistence required but save failed")
                        else:
                            logger.warning(f"Failed to save model '{model_id}' to persistence backend (running in-memory only)")

                except DuplicateKeyError:
                    # Duplicate key error (concurrent registration)
                    logger.warning(f"Model '{model_id}' already exists in persistence backend (concurrent registration)")
                    saved = True
                except HTTPException:
                    raise  # Re-raise HTTPException unchanged
                except Exception as e:
                    # Unexpected error during persistence save
                    # CRITICAL SECURITY: Sanitize error message to prevent API key exposure
                    sanitized_error = sanitize_error_message(str(e))
                    logger.error(f"Error saving model '{model_id}' to persistence backend: {sanitized_error}")
                    raise HTTPException(500, truncate_error(f"Failed to persist model: {sanitized_error}"))

                # Register in global registries (atomic operation with proper rollback)
                # CRITICAL FIX: Single authoritative check inside lock eliminates TOCTOU race
                client_to_close = None
                with _registry_lock:
                    # Final authoritative collision check
                    if model_id in _replicate_clients or model_id in _llm_models_config:
                        # Concurrent registration detected - treat as idempotent success
                        client_to_close = client
                        client_created = False  # Don't clean up in outer except
                        logger.info(f"Model '{model_id}' concurrently registered; treating as no-op")
                    else:
                        # Atomically register both in replicate clients and provider registry
                        _replicate_clients[model_id] = client
                        _llm_models_config[model_id] = model_config
                        client_created = False  # Successfully registered, don't clean up

                # Close outside lock if concurrent registration detected
                if client_to_close:
                    await client_to_close.close()

            except Exception as e:
                # Rollback: Clean up client if it was created but not registered
                if client_created:
                    try:
                        await client.close()
                        logger.debug(f"Cleaned up client for model '{model_id}' after registration failure")
                    except Exception as cleanup_error:
                        logger.debug(f"Failed to clean up client during rollback: {cleanup_error}")
                raise

            logger.info(f"Successfully registered Replicate model: {model_id}")

            # Audit log successful registration (reuse db variable from above)
            await log_audit_event(
                db=db,
                action="register_model",
                model_id=model_id,
                client_ip=client_ip,
                changes={"type": "replicate", "model": config.model, "persisted": saved},
                status="success"
            )

            return {
                "message": f"Model '{model_id}' registered successfully",
                "model_id": model_id,
                "type": "replicate",
                "status": "active",
                "persisted": saved
            }

        except HTTPException as e:
            # Audit log failed registration (only if db was initialized)
            if db is not None:
                try:
                    await log_audit_event(
                        db=db,
                        action="register_model",
                        model_id=model_id,
                        client_ip=client_ip,
                        status="failure",
                        error_message=str(e.detail)
                    )
                except Exception:
                    pass  # Audit logging failure should not mask original error
            # Re-raise HTTPException unchanged (preserves status code)
            raise
        except ValueError as e:
            # Client errors (bad parameters)
            # CRITICAL SECURITY: Sanitize error message to prevent API key exposure
            sanitized_error = sanitize_error_message(str(e))
            logger.error(f"Invalid configuration for Replicate model '{model_id}': {sanitized_error}")
            raise HTTPException(400, f"Invalid model configuration: {sanitized_error}")
        except Exception as e:
            # Server errors (unexpected failures)
            # CRITICAL SECURITY: Sanitize error message to prevent API key exposure
            sanitized_error = sanitize_error_message(str(e))
            logger.error(f"Failed to register Replicate model '{model_id}': {sanitized_error}")
            raise HTTPException(500, truncate_error(f"Failed to register model: {sanitized_error}"))

    elif model_type in ("vllm", "ollama", "lmstudio"):
        # Import LLM launcher and registry functions
        from ..services.llm_launcher import launch_single_llm_model
        from ..services.run_servers import get_llm_processes, register_llm_process
        from ..services.llm_provider_registry import _registry_lock, _llm_models_config

        try:
            # Early check for existing model
            llm_processes = get_llm_processes()
            with _registry_lock:
                if model_id in llm_processes:
                    raise HTTPException(400, f"Model '{model_id}' already registered as {model_type} model")
                if model_id in _llm_models_config:
                    raise HTTPException(400, f"Model '{model_id}' already registered in provider registry")

            # Extract model config from request
            model_config = config.model_dump()
            model_config.pop("model_id", None)
            model_config.pop("type", None)

            # Save to persistence backend FIRST (before launching process)
            try:
                saved = await db.save_llm_model(config.model_dump())
                if not saved:
                    require_persistence = os.getenv("REQUIRE_MONGODB_PERSISTENCE", "false").lower() == "true"
                    if require_persistence:
                        raise HTTPException(500, "Persistence required but save failed")
                    else:
                        logger.warning(f"Failed to save model '{model_id}' to persistence backend (running in-memory only)")

            except DuplicateKeyError:
                logger.warning(f"Model '{model_id}' already exists in persistence backend (concurrent registration)")
                saved = True
            except HTTPException:
                raise
            except Exception as e:
                sanitized_error = sanitize_error_message(str(e))
                logger.error(f"Error saving model '{model_id}' to persistence backend: {sanitized_error}")
                raise HTTPException(500, truncate_error(f"Failed to persist model: {sanitized_error}"))

            # Launch the LLM process
            process = launch_single_llm_model(model_id, model_config)

            if not process:
                raise HTTPException(500, f"Failed to launch {model_type} model '{model_id}'")

            # Register in global registries
            process_registered = False
            try:
                with _registry_lock:
                    # Final check for concurrent registration
                    if model_id not in llm_processes and model_id not in _llm_models_config:
                        # Direct assignment to avoid nested lock acquisition
                        llm_processes[model_id] = process
                        _llm_models_config[model_id] = model_config
                        process_registered = True
                        logger.info(f"✓ Registered {model_type} model: {model_id}")
                    else:
                        logger.info(f"⚠ Model '{model_id}' concurrently registered; stopping duplicate")

                # If concurrent registration detected, stop the process we just launched
                if not process_registered:
                    try:
                        process.stop()
                    except Exception as stop_error:
                        logger.debug(f"Failed to stop duplicate process: {stop_error}")

            except Exception as e:
                # Rollback: Stop process if registration failed
                try:
                    process.stop()
                    logger.debug(f"Cleaned up process for model '{model_id}' after registration failure")
                except Exception as cleanup_error:
                    logger.debug(f"Failed to clean up process during rollback: {cleanup_error}")
                raise

            logger.info(f"Successfully registered {model_type} model: {model_id}")

            # Audit log
            await log_audit_event(
                db=db,
                action="register_model",
                model_id=model_id,
                client_ip=client_ip,
                changes={"type": model_type, "config": model_config, "persisted": saved},
                status="success"
            )

            return {
                "message": f"Model '{model_id}' registered successfully",
                "model_id": model_id,
                "type": model_type,
                "status": "running",
                "persisted": saved
            }

        except HTTPException as e:
            # Audit log failed registration
            if db is not None:
                try:
                    await log_audit_event(
                        db=db,
                        action="register_model",
                        model_id=model_id,
                        client_ip=client_ip,
                        status="failure",
                        error_message=str(e.detail)
                    )
                except Exception:
                    pass
            raise
        except Exception as e:
            sanitized_error = sanitize_error_message(str(e))
            logger.error(f"Failed to register {model_type} model '{model_id}': {sanitized_error}")
            raise HTTPException(500, truncate_error(f"Failed to register model: {sanitized_error}"))

    else:
        raise HTTPException(400, f"Unsupported model type: {model_type}")


@router.delete("/llm/models/{model_id}")
async def unregister_llm_model(
    request: Request,
    model_id: str,
    token: str = Depends(get_token)
):
    """
    Unregister an LLM model.

    Rate limit: 20 requests per minute per client.

    Args:
        model_id: Model identifier to remove

    Returns:
        Success message
    """
    from ..services.replicate_client import _replicate_clients
    from ..services.llm_provider_registry import _registry_lock
    from ..services.llm_provider_registry import _llm_models_config

    # NEW COPILOT COMMENT 2 FIX: Validate model_id path parameter
    validate_model_id(model_id)

    # Apply rate limiting
    client_ip = get_client_ip(request)
    rate_limit_key = get_rate_limit_key("delete_model", token, client_ip)
    max_requests, window_seconds = RATE_LIMIT_MODEL_DELETE
    check_rate_limit(rate_limit_key, max_requests=max_requests, window_seconds=window_seconds)

    # Attempt to remove model from Replicate clients registry
    client = None
    with _registry_lock:
        client = _replicate_clients.pop(model_id, None)

        # If model is not a Replicate client and not in the LLM provider registry, it's unknown
        if client is None and model_id not in _llm_models_config:
            raise HTTPException(404, f"Model '{model_id}' not found")

        # Remove from LLM provider registry (protected by same lock for consistency)
        _llm_models_config.pop(model_id, None)

    # Stop the Replicate client if it existed
    if client is not None:
        try:
            await client.close()
        except Exception as exc:
            logger.error(f"Error while closing client for model '{model_id}': {exc}")

    # Delete from MongoDB for persistence (if supported by the backend)
    db = get_database_manager(request)
    deleted = await db.delete_llm_model(model_id)
    if not deleted:
        logger.warning(f"Failed to delete model '{model_id}' from persistence backend")

    logger.info(f"Successfully unregistered model: {model_id}")

    # Audit log successful deletion
    await log_audit_event(
        db=db,
        action="delete_model",
        model_id=model_id,
        client_ip=client_ip,
        changes={"persisted": deleted},
        status="success"
    )

    return {
        "message": f"Model '{model_id}' unregistered successfully",
        "model_id": model_id,
        "persisted": deleted
    }


@router.patch("/llm/models/{model_id}")
async def update_llm_model(
    request: Request,
    model_id: str,
    updates: Dict[str, Any] = Body(...),
    token: str = Depends(get_token)
):
    """
    Update LLM model configuration.

    Only these fields can be updated:
    - default_params (dict): Default inference parameters
    - timeout (int): Request timeout in seconds (10-3600)
    - max_retries (int): Maximum retry attempts (0-10)

    Cannot update: model_id, type, model, api_key (requires re-registration)

    Rate limit: 20 requests per minute per client.

    Args:
        model_id: Model identifier to update
        updates: Dictionary of fields to update

    Returns:
        Success message with updated fields
    """
    from ..services.replicate_client import _replicate_clients
    from ..services.llm_provider_registry import _registry_lock
    from ..services.llm_provider_registry import _llm_models_config

    # NEW COPILOT COMMENT 2 FIX: Validate model_id path parameter
    validate_model_id(model_id)

    # Apply rate limiting
    client_ip = get_client_ip(request)
    rate_limit_key = get_rate_limit_key("update_model", token, client_ip)
    max_requests, window_seconds = RATE_LIMIT_MODEL_UPDATE
    check_rate_limit(rate_limit_key, max_requests=max_requests, window_seconds=window_seconds)

    # Check model exists
    with _registry_lock:
        if model_id not in _replicate_clients and model_id not in _llm_models_config:
            raise HTTPException(404, f"Model '{model_id}' not found")

        config = _llm_models_config.get(model_id, {}).copy()

    # Validate updatable fields
    # CRITICAL SECURITY: Explicitly check for attempts to update sensitive fields
    sensitive_fields = {'api_key', 'api_token', 'auth_token', 'password', 'secret', 'token', 'bearer_token'}
    attempted_sensitive = set(updates.keys()) & sensitive_fields
    if attempted_sensitive:
        raise HTTPException(
            400,
            f"Cannot update sensitive authentication fields: {attempted_sensitive}. "
            f"To change API keys, please delete and re-register the model."
        )

    allowed_updates = {'default_params', 'timeout', 'max_retries'}
    invalid = set(updates.keys()) - allowed_updates
    if invalid:
        raise HTTPException(400, f"Cannot update fields: {invalid}. Allowed: {allowed_updates}")

    # Validate field values
    if 'timeout' in updates:
        timeout = updates['timeout']
        if not isinstance(timeout, int) or not (10 <= timeout <= 3600):
            raise HTTPException(400, f"timeout must be integer between 10 and 3600, got {timeout}")

    if 'max_retries' in updates:
        max_retries = updates['max_retries']
        if not isinstance(max_retries, int) or not (0 <= max_retries <= 10):
            raise HTTPException(400, f"max_retries must be integer between 0 and 10, got {max_retries}")

    if 'default_params' in updates:
        params = updates['default_params']
        if not isinstance(params, dict):
            raise HTTPException(400, "default_params must be a dictionary")

        # Validate parameter keys and values
        allowed_keys = {'temperature', 'max_tokens', 'top_p', 'top_k', 'stop', 'frequency_penalty', 'presence_penalty'}
        invalid_keys = set(params.keys()) - allowed_keys
        if invalid_keys:
            raise HTTPException(400, f"Invalid parameters: {invalid_keys}. Allowed: {allowed_keys}")

        # Use shared validation functions
        try:
            validate_inference_params(params)
        except ValueError as e:
            raise HTTPException(400, str(e))

    # COPILOT FIX: Save old values for potential rollback
    old_config = None
    old_client_state = {}
    with _registry_lock:
        # Save current state for rollback
        old_config = _llm_models_config[model_id].copy()

        client = _replicate_clients.get(model_id)
        if client is not None:
            old_client_state = {
                'default_params': client.default_params.copy() if hasattr(client, 'default_params') and isinstance(client.default_params, dict) else None,
                'timeout': getattr(client, 'timeout', None),
                'max_retries': getattr(client, 'max_retries', None)
            }

        # Update in-memory config AND live client instance (hold lock during attribute updates)
        _llm_models_config[model_id].update(updates)

        # Update live ReplicateClient instance if it exists
        # CRITICAL: All client attribute updates must happen inside lock to prevent
        # race conditions with concurrent requests using the client
        if client is not None:
            if 'default_params' in updates:
                client.default_params = updates['default_params']
            if 'timeout' in updates:
                client.timeout = updates['timeout']
            if 'max_retries' in updates:
                client.max_retries = updates['max_retries']

    # Update in MongoDB (use update_llm_model, not save_llm_model)
    db = get_database_manager(request)
    saved = False
    saved = await db.update_llm_model(model_id, updates)

    # COPILOT FIX: If persistence fails and REQUIRE_MONGODB_PERSISTENCE is set, rollback in-memory changes
    require_persistence = os.getenv("REQUIRE_MONGODB_PERSISTENCE", "false").lower() == "true"
    if not saved:
        if require_persistence:
            logger.error(f"Failed to persist model '{model_id}' update to MongoDB - rolling back in-memory changes")

            # Rollback in-memory state
            with _registry_lock:
                _llm_models_config[model_id] = old_config

                client = _replicate_clients.get(model_id)
                if client is not None and old_client_state:
                    if old_client_state['default_params'] is not None:
                        client.default_params = old_client_state['default_params']
                    if old_client_state['timeout'] is not None:
                        client.timeout = old_client_state['timeout']
                    if old_client_state['max_retries'] is not None:
                        client.max_retries = old_client_state['max_retries']

            raise HTTPException(500, f"Failed to persist model '{model_id}' update to MongoDB (REQUIRE_MONGODB_PERSISTENCE=true)")
        else:
            logger.warning(f"Failed to update model '{model_id}' in persistence backend (in-memory update succeeded)")

    logger.info(f"Successfully updated model: {model_id}")

    # Audit log successful update (reuse db variable)
    try:
        await log_audit_event(
            db=db,
            action="update_model",
            model_id=model_id,
            client_ip=client_ip,
            changes={"updated_fields": list(updates.keys()), "values": sanitize_audit_changes(updates), "persisted": saved},
            status="success"
        )
    except Exception:
        pass  # Audit logging failure should not break operation

    return {
        "message": f"Model '{model_id}' updated successfully",
        "model_id": model_id,
        "updated_fields": list(updates.keys()),
        "persisted": saved
    }


@router.post("/llm/models/{model_id}/rollback")
async def rollback_llm_model(
    request: Request,
    model_id: str,
    version: Optional[int] = Query(None, description="Specific version to rollback to (None = most recent)"),
    token: str = Depends(get_token)
):
    """
    Rollback LLM model to a previous version.

    Requires MongoDB persistence. Retrieves model configuration from version history
    and restores it to the main collection.

    Rate limit: 10 requests per minute per client.

    Args:
        model_id: Model identifier to rollback
        version: Specific version number to rollback to (optional, defaults to most recent)

    Returns:
        Success message with restored version number
    """
    from ..services.replicate_client import _replicate_clients
    from ..services.llm_provider_registry import _registry_lock
    from ..services.llm_provider_registry import _llm_models_config

    # NEW COPILOT COMMENT 2 FIX: Validate model_id path parameter
    validate_model_id(model_id)

    # Apply rate limiting
    client_ip = get_client_ip(request)
    rate_limit_key = get_rate_limit_key("rollback_model", token, client_ip)
    max_requests, window_seconds = RATE_LIMIT_MODEL_ROLLBACK
    check_rate_limit(rate_limit_key, max_requests=max_requests, window_seconds=window_seconds)

    # Get database manager
    db = get_database_manager(request)

    # Check if rollback is supported
    if not db.supports_rollback():
        raise HTTPException(
            501,
            "Model rollback requires a persistence backend with versioning support (current backend does not support versioning)"
        )

    # Perform rollback in database
    try:
        rolled_back = await db.rollback_llm_model(model_id, version)
        if not rolled_back:
            raise HTTPException(
                404,
                f"No version history found for model '{model_id}'"
                + (f" with version {version}" if version else "")
            )
    except Exception as e:
        # CRITICAL SECURITY: Sanitize error message to prevent API key exposure
        sanitized_error = sanitize_error_message(str(e))
        logger.error(f"Error rolling back model '{model_id}': {sanitized_error}")
        raise HTTPException(500, truncate_error(f"Failed to rollback model: {sanitized_error}"))

    # Reload model configuration from database into in-memory registries
    try:
        restored_config = await db.get_llm_model(model_id)
        if not restored_config:
            raise HTTPException(500, "Model rolled back in database but failed to retrieve config")

        # Update in-memory registries if this is a Replicate model
        if restored_config.get("type") == "replicate":
            from ..services.replicate_client import ReplicateClient

            # Close existing client if present (pop from registry first to avoid holding lock during await)
            client_to_close = None
            with _registry_lock:
                if model_id in _replicate_clients:
                    client_to_close = _replicate_clients.pop(model_id, None)

            if client_to_close is not None:
                try:
                    await client_to_close.close()
                except Exception:
                    pass  # Best effort cleanup

            # Re-initialize client with restored config
            model_config = {k: v for k, v in restored_config.items() if k != "model_id"}
            client = ReplicateClient(model_id, model_config)

            # Verify health
            if not await client.health_check():
                logger.warning(f"Health check failed after rollback for model '{model_id}'")

            # Update registries
            with _registry_lock:
                _replicate_clients[model_id] = client
                _llm_models_config[model_id] = model_config

        restored_version = restored_config.get("version", "unknown")

        # Audit log rollback
        try:
            await log_audit_event(
                db=db,
                action="rollback_model",
                model_id=model_id,
                client_ip=client_ip,
                changes={"target_version": version, "restored_version": restored_version},
                status="success"
            )
        except Exception:
            pass  # Audit logging failure should not break operation

        return {
            "message": f"Model '{model_id}' rolled back successfully",
            "model_id": model_id,
            "version": restored_version
        }

    except HTTPException:
        raise
    except Exception as e:
        # CRITICAL SECURITY: Sanitize error message to prevent API key exposure
        sanitized_error = sanitize_error_message(str(e))
        logger.error(f"Error reloading model '{model_id}' after rollback: {sanitized_error}")
        # NEW COPILOT COMMENT 4 FIX: Use 500 instead of 206 (Partial Content is for Range requests)
        # Database operation succeeded but in-memory reload failed = server-side failure
        raise HTTPException(
            status_code=500,
            detail=f"Model '{model_id}' was rolled back in the database but failed to reload into in-memory registries: {sanitized_error}"
        )


# ============================================================================
# vLLM Omni Multimodal Generation Endpoints
# Image and video generation via Replicate integration
# ============================================================================

@router.post("/llm/v1/generate/image")
async def generate_image(
    request_body: Dict[str, Any] = Body(...),
    token: str = Depends(get_token)
):
    """
    Generate image from text prompt (text-to-image).

    OpenAI-compatible endpoint. Works with Replicate image generation models
    (FLUX, Stable Diffusion, etc.). Validates that model supports 'text-to-image' capability.

    Args:
        request_body: Generation parameters including model and prompt

    Returns:
        Prediction response with prediction_id and status

    Example:
        {
          "model": "flux-image-gen",
          "prompt": "A serene Japanese garden with cherry blossoms",
          "aspect_ratio": "16:9"
        }
    """
    # Extract model from request body (OpenAI-compatible format)
    model_id = request_body.get("model")
    if not model_id:
        raise HTTPException(400, "Missing 'model' field in request body")

    # Get model config and validate it exists
    model_config = get_model_config(model_id)
    if not model_config:
        raise HTTPException(404, f"Model '{model_id}' not found in configuration")

    # Validate provider type
    provider_type = get_model_type(model_id)
    if provider_type != "replicate":
        raise HTTPException(
            400,
            f"Image generation only supported for Replicate models. "
            f"Model '{model_id}' is type '{provider_type}'"
        )

    # Remove 'model' field from payload before sending to Replicate
    payload = {k: v for k, v in request_body.items() if k != "model"}

    # Record metrics for image generation
    collector = get_metrics_collector()
    start_time = collector.record_request_start(model_id, provider_type)

    # Get or create Replicate client
    client = get_replicate_client(model_id)
    created_temp_client = False
    if not client:
        # Create temporary client for on-demand generation
        client = ReplicateClient(model_id, model_config)
        created_temp_client = True

    try:
        result = await omni_adapter.generate_image(model_id, model_config, payload, client)
        # Record success metrics
        collector.record_request_success(
            model_id,
            start_time,
            prompt_tokens=0,  # Image generation doesn't use tokens
            completion_tokens=0
        )
        return result
    except HTTPException as e:
        # Record failure metrics
        collector.record_request_failure(model_id, start_time, e.status_code)
        raise
    except Exception:
        # Record unexpected failure with status 500
        collector.record_request_failure(model_id, start_time, 500)
        raise
    finally:
        # Ensure any temporary client is closed to avoid resource leaks
        if created_temp_client:
            await client.close()


@router.post("/llm/v1/generate/video")
async def generate_video(
    request_body: Dict[str, Any] = Body(...),
    token: str = Depends(get_token)
):
    """
    Generate video from text prompt (text-to-video).

    OpenAI-compatible endpoint. Supports video generation models like
    Google Veo 3, Kling v2.6, etc. Validates that model supports
    'text-to-video' capability.

    Args:
        request_body: Generation parameters including model and prompt

    Returns:
        Prediction response with prediction_id and status

    Example:
        {
          "model": "veo-video",
          "prompt": "一只熊猫在雨中弹吉他 (A panda playing guitar in the rain)",
          "duration": 5,
          "fps": 24
        }
    """
    # Extract model from request body (OpenAI-compatible format)
    model_id = request_body.get("model")
    if not model_id:
        raise HTTPException(400, "Missing 'model' field in request body")

    # Get model config and validate it exists
    model_config = get_model_config(model_id)
    if not model_config:
        raise HTTPException(404, f"Model '{model_id}' not found in configuration")

    # Validate provider type
    provider_type = get_model_type(model_id)
    if provider_type != "replicate":
        raise HTTPException(
            400,
            f"Video generation only supported for Replicate models. "
            f"Model '{model_id}' is type '{provider_type}'"
        )

    # Remove 'model' field from payload before sending to Replicate
    payload = {k: v for k, v in request_body.items() if k != "model"}

    # Record metrics for video generation
    collector = get_metrics_collector()
    start_time = collector.record_request_start(model_id, provider_type)

    # Get or create Replicate client
    client = get_replicate_client(model_id)
    created_temp_client = False
    if not client:
        # Create temporary client for on-demand generation
        client = ReplicateClient(model_id, model_config)
        created_temp_client = True

    try:
        result = await omni_adapter.generate_video(model_id, model_config, payload, client)
        # Record success metrics
        collector.record_request_success(
            model_id,
            start_time,
            prompt_tokens=0,  # Video generation doesn't use tokens
            completion_tokens=0
        )
        return result
    except HTTPException as e:
        # Record failure metrics
        collector.record_request_failure(model_id, start_time, e.status_code)
        raise
    except Exception:
        # Record unexpected failure with status 500
        collector.record_request_failure(model_id, start_time, 500)
        raise
    finally:
        # Ensure any temporary client is closed to avoid resource leaks
        if created_temp_client:
            await client.close()


@router.post("/llm/v1/animate")
async def animate_image(
    request_body: Dict[str, Any] = Body(...),
    token: str = Depends(get_token)
):
    """
    Animate image into video (image-to-video).

    OpenAI-compatible endpoint. Supports models like Kling v2.6.
    Validates that model supports 'image-to-video' capability.

    Args:
        request_body: Animation parameters including model and image

    Returns:
        Prediction response with prediction_id and status

    Example:
        {
          "model": "kling-animate",
          "image_url": "https://example.com/photo.jpg",
          "motion_bucket_id": 127,
          "fps": 24
        }
    """
    # Extract model from request body (OpenAI-compatible format)
    model_id = request_body.get("model")
    if not model_id:
        raise HTTPException(400, "Missing 'model' field in request body")

    # Get model config and validate it exists
    model_config = get_model_config(model_id)
    if not model_config:
        raise HTTPException(404, f"Model '{model_id}' not found in configuration")

    # Validate provider type
    provider_type = get_model_type(model_id)
    if provider_type != "replicate":
        raise HTTPException(
            400,
            f"Image animation only supported for Replicate models. "
            f"Model '{model_id}' is type '{provider_type}'"
        )

    # Remove 'model' field from payload before sending to Replicate
    payload = {k: v for k, v in request_body.items() if k != "model"}

    # Record metrics for image animation
    collector = get_metrics_collector()
    start_time = collector.record_request_start(model_id, provider_type)

    # Get or create Replicate client
    client = get_replicate_client(model_id)
    created_temp_client = False
    if not client:
        # Create temporary client for on-demand generation
        client = ReplicateClient(model_id, model_config)
        created_temp_client = True

    try:
        result = await omni_adapter.animate_image(model_id, model_config, payload, client)
        # Record success metrics
        collector.record_request_success(
            model_id,
            start_time,
            prompt_tokens=0,  # Image animation doesn't use tokens
            completion_tokens=0
        )
        return result
    except HTTPException as e:
        # Record failure metrics
        collector.record_request_failure(model_id, start_time, e.status_code)
        raise
    except Exception:
        # Record unexpected failure with status 500
        collector.record_request_failure(model_id, start_time, 500)
        raise
    finally:
        # Ensure any temporary client is closed to avoid resource leaks
        if created_temp_client:
            await client.close()


@router.get("/llm/predictions/{prediction_id}")
async def get_generation_status(
    prediction_id: str,
    token: str = Depends(get_token)
):
    """
    Check status of async generation (image/video).

    Returns prediction status and output URLs when complete.
    Works for any Replicate prediction (image, video, animation).

    Args:
        prediction_id: Replicate prediction ID

    Returns:
        Prediction status with output URLs

    Example response:
        {
          "id": "abc123",
          "status": "succeeded",
          "output": ["https://replicate.delivery/image.png"]
        }
    """
    # Try to get Replicate API token from configured models first
    api_token = None
    replicate_models = list_models_by_type("replicate")

    if replicate_models:
        # Use the first configured Replicate model's token
        first_model_id = replicate_models[0]
        first_model_config = get_model_config(first_model_id)
        if first_model_config:
            config_token = first_model_config.get("api_key")
            # Only use non-placeholder, non-empty tokens from config
            if config_token and not is_placeholder(config_token):
                api_token = config_token

    # Fallback to environment variable if no configured models or only placeholders
    if not api_token:
        api_token = os.getenv("REPLICATE_API_TOKEN")

    if not api_token:
        raise HTTPException(
            503,
            "No Replicate API token configured. Either add a Replicate model to your config "
            "or set REPLICATE_API_TOKEN environment variable."
        )

    # Record metrics for status check
    collector = get_metrics_collector()
    start_time = collector.record_request_start("status-check", "replicate")

    # Create a minimal client just for fetching prediction status
    # The prediction_id contains all necessary information for Replicate
    client = ReplicateClient("status-check", {"model": "dummy", "api_key": api_token})
    try:
        result = await omni_adapter.get_generation_status(prediction_id, client)
        # Record success metrics
        collector.record_request_success(
            "status-check",
            start_time,
            prompt_tokens=0,
            completion_tokens=0
        )
        return result
    except HTTPException as e:
        # Record failure metrics
        collector.record_request_failure("status-check", start_time, e.status_code)
        raise
    except Exception:
        # Record unexpected failure with status 500
        collector.record_request_failure("status-check", start_time, 500)
        raise
    finally:
        # Ensure the temporary client is closed to avoid resource leaks
        await client.close()


