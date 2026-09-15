"""Pre-flight configuration validation for MCP servers.

Catches the missing-credential case *before* launch, instead of waiting for the
server to crash or to fail at its first tool call. Without this, a server
configured with `DB_PASSWORD=<your-password>` starts cleanly and looks healthy
until someone actually calls a tool.

**Values are never returned or logged** — only key names. These are credentials.

Default behaviour is warn-and-start, not block: a server may legitimately read
credentials from a mounted file or an inherited environment, and refusing to
start would turn a monitoring feature into an outage. Opt into blocking per
server with ``"strict_config": true``, or globally with ``FMCP_STRICT_CONFIG=true``.
"""

import os
import shutil
from typing import Any, Dict, List, Optional

from loguru import logger

from ..utils.env_utils import has_env_var_syntax, is_placeholder

#: Env keys whose absence is worth flagging even when not declared required,
#: because their names indicate a credential the server almost certainly needs.
_CREDENTIAL_HINTS = (
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "credential", "private_key", "access_key", "auth",
)


def _is_credential_key(key: str) -> bool:
    lowered = key.lower()
    return any(hint in lowered for hint in _CREDENTIAL_HINTS)


def validate_server_config(
    server_id: str,
    config: Dict[str, Any],
    resolved_env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Validate a server's config before spawning it.

    Args:
        server_id: Server identifier (for messages).
        config: The server config dict (command, args, env, required_env, ...).
        resolved_env: The env actually about to be passed to the subprocess, if
            already computed. Falls back to ``config["env"]``.

    Returns:
        ``{"valid", "blocking", "missing_env", "placeholder_env",
        "unresolved_env", "errors", "warnings", "remediation"}``

        ``valid`` is False when anything was found; ``blocking`` is True only
        when strict mode is on *and* a real problem exists.
    """
    env: Dict[str, str] = dict(resolved_env if resolved_env is not None else config.get("env") or {})

    missing_env: List[str] = []
    placeholder_env: List[str] = []
    unresolved_env: List[str] = []
    errors: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []

    # ── Declared required env ─────────────────────────────────────────────
    required = config.get("required_env") or []
    if isinstance(required, dict):  # tolerate {"KEY": "description"} form
        required = list(required.keys())

    for key in required:
        value = env.get(key) or os.environ.get(key)
        if value is None or not str(value).strip():
            missing_env.append(key)
            errors.append({
                "key": key,
                "problem": "required but not set",
                "impact": "the server will not be able to authenticate or connect",
            })

    # ── Placeholder and unresolved values in the provided env ─────────────
    for key, value in env.items():
        if not isinstance(value, str):
            continue

        if has_env_var_syntax(value):
            # A surviving ${VAR} means the referenced variable was never set.
            unresolved_env.append(key)
            errors.append({
                "key": key,
                "problem": "contains an unresolved environment-variable reference",
                "impact": "the server will receive the literal placeholder text, not a value",
            })
            continue

        if is_placeholder(value):
            placeholder_env.append(key)
            entry = {
                "key": key,
                "problem": "holds a placeholder value",
                "impact": "the server will fail to authenticate against its dependency",
            }
            # A placeholder in something named like a credential is an error;
            # elsewhere it may be a deliberate sentinel.
            (errors if _is_credential_key(key) else warnings).append(entry)

    # ── Command reachability ──────────────────────────────────────────────
    # Reported here as a config error rather than surfacing later as exit 127.
    command = config.get("command")
    if command and isinstance(command, str):
        if not shutil.which(command) and not os.path.isfile(command):
            errors.append({
                "key": "command",
                "problem": f"'{command}' not found on PATH",
                "impact": "the server cannot start (would exit with code 127)",
            })

    strict = bool(config.get("strict_config",
                             os.getenv("FMCP_STRICT_CONFIG", "").lower() == "true"))

    result = {
        "valid": not errors and not warnings,
        "blocking": bool(strict and errors),
        "missing_env": missing_env,
        "placeholder_env": placeholder_env,
        "unresolved_env": unresolved_env,
        "errors": errors,
        "warnings": warnings,
        "remediation": _remediation(server_id, missing_env, placeholder_env,
                                    unresolved_env, errors),
    }

    if errors:
        keys = ", ".join(sorted({e["key"] for e in errors}))
        logger.warning(
            f"[config] Server '{server_id}' has configuration problems: {keys}"
            f"{' — refusing to start (strict_config)' if result['blocking'] else ''}"
        )
    elif warnings:
        keys = ", ".join(sorted({w["key"] for w in warnings}))
        logger.info(f"[config] Server '{server_id}' configuration warnings: {keys}")

    return result


def _remediation(
    server_id: str,
    missing: List[str],
    placeholder: List[str],
    unresolved: List[str],
    errors: List[Dict[str, str]],
) -> str:
    """Build a paste-into-a-ticket remediation sentence."""
    if not errors:
        return ""

    parts: List[str] = []
    if missing:
        parts.append(f"set {', '.join(missing)}")
    if placeholder:
        parts.append(f"replace the placeholder value for {', '.join(placeholder)}")
    if unresolved:
        parts.append(
            f"define the referenced variable(s) for {', '.join(unresolved)} in the "
            f"gateway environment"
        )

    command_error = next((e for e in errors if e["key"] == "command"), None)
    if command_error:
        parts.append(f"install or fix the command ({command_error['problem']})")

    if not parts:
        return ""

    action = "; ".join(parts)
    return (
        f"For server '{server_id}': {action}. Environment variables can be updated "
        f"via PUT /api/servers/{server_id}/instance/env, then restart the server."
    )
