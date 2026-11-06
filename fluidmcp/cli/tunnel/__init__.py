"""
Built-in tunnel to GPT Engine (fmcp-tunnel/1).

Off unless FMCP_TUNNEL_URL is set; the websockets and cryptography imports happen only then.
"""

import importlib.metadata
import os
from typing import TYPE_CHECKING, Iterable, Optional
from urllib.parse import urlparse

from loguru import logger

if TYPE_CHECKING:
    from .client import TunnelClient

# Without FMCP_TUNNEL_ALLOW_ANY_HOST=true, the tunnel only connects to hosts under *.fluidgpt.ai.
ALLOWED_DOMAIN = "fluidgpt.ai"


def _is_allowed_domain(host: str) -> bool:
    """True for a subdomain of ALLOWED_DOMAIN (site-a.fluidgpt.ai), not the bare domain or a look-alike."""
    labels = host.rstrip(".").split(".")
    return len(labels) > 2 and labels[-2:] == ALLOWED_DOMAIN.split(".") and all(labels)


def _allow_any_host() -> bool:
    """Read FMCP_TUNNEL_ALLOW_ANY_HOST: only "true" turns the host restriction off."""
    value =os.environ.get("FMCP_TUNNEL_ALLOW_ANY_HOST", "").strip().lower()
    if value in ("", "false"):
        return False
    if value == "true":
        return True
    logger.warning(f"FMCP_TUNNEL_ALLOW_ANY_HOST={value!r} is not 'true' or 'false'; treating it as false")
    return False


def tunnel_from_env(gateway_port: int, configured_servers: Iterable[str] = ()) -> Optional["TunnelClient"]:
    """
    Build a TunnelClient from FMCP_TUNNEL_* settings.

    Returns None when the tunnel is not configured, or when the settings are invalid
    (the reason is logged; the gateway keeps running without the tunnel).
    """
    url = os.environ.get("FMCP_TUNNEL_URL", "").strip()
    if not url:
        return None

    try:
        from .client import TunnelClient
        from .keys import key_path, load_identity_key
        from .protocol import CID_RE, parse_public_key_list
    except ImportError as e:
        logger.error(f"Tunnel disabled: missing dependency '{e.name}' (pip install websockets cryptography)")
        return None

    errors = []
    allow_any_host = _allow_any_host()
    parsed = urlparse(url)
    host = parsed.hostname or ""
    local = parsed.scheme == "ws" and host in ("localhost", "127.0.0.1")
    if not (parsed.scheme == "wss" or local):
        errors.append("FMCP_TUNNEL_URL must start with wss:// (ws:// is accepted only for localhost testing)")
    elif parsed.username or parsed.password:
        errors.append("FMCP_TUNNEL_URL must not contain a user name or password")
    elif not (local or allow_any_host or _is_allowed_domain(host)):
        errors.append(f"FMCP_TUNNEL_URL host {host or '(none)'} is not under *.{ALLOWED_DOMAIN} "
                      f"(set FMCP_TUNNEL_ALLOW_ANY_HOST=true for test setups)")
    token = os.environ.get("FMCP_TUNNEL_TOKEN", "").strip()
    if not token:
        errors.append("FMCP_TUNNEL_TOKEN is required")
    connector_id = os.environ.get("FMCP_TUNNEL_CONNECTOR_ID", "").strip()
    if not CID_RE.match(connector_id):
        errors.append("FMCP_TUNNEL_CONNECTOR_ID is required (letters, digits, . _ : -; max 64)")
    allowed = [s.strip() for s in os.environ.get("FMCP_TUNNEL_ALLOWED_SERVERS", "").split(",") if s.strip()]
    if not allowed:
        errors.append("FMCP_TUNNEL_ALLOWED_SERVERS is required")
    server_keys = ()
    try:
        server_keys = parse_public_key_list(os.environ.get("FMCP_TUNNEL_SERVER_PUBLIC_KEYS", ""))
    except ValueError as e:
        errors.append(f"FMCP_TUNNEL_SERVER_PUBLIC_KEYS is invalid ({e})")
    try:
        max_concurrency = int(os.environ.get("FMCP_TUNNEL_MAX_CONCURRENCY", "20"))
        request_timeout = float(os.environ.get("FMCP_TUNNEL_REQUEST_TIMEOUT", "45"))
    except ValueError:
        errors.append("FMCP_TUNNEL_MAX_CONCURRENCY and FMCP_TUNNEL_REQUEST_TIMEOUT must be numbers")
    if errors:
        logger.error(f"Tunnel disabled: {'; '.join(errors)}")
        return None

    try:
        identity_key = load_identity_key()
    except FileNotFoundError:
        logger.error(f"Tunnel disabled: no identity key at {key_path()}; create one with: fmcp tunnel keygen")
        return None
    except (PermissionError, ValueError) as e:
        logger.error(f"Tunnel disabled: cannot use identity key at {key_path()} ({e})")
        return None

    host_override = allow_any_host and not local and not _is_allowed_domain(host)
    if host_override:
        logger.warning(f"FMCP_TUNNEL_ALLOW_ANY_HOST=true: tunnel host {host} is not restricted to *.{ALLOWED_DOMAIN}")
    elif allow_any_host:
        logger.info("FMCP_TUNNEL_ALLOW_ANY_HOST=true is not needed for this URL; remove it")

    unknown = sorted(set(allowed) - set(configured_servers))
    if unknown:
        logger.warning(f"Tunnel allowlist names servers that are not configured: {', '.join(unknown)}")

    local_token = os.environ.get("FMCP_BEARER_TOKEN") if os.environ.get("FMCP_SECURE_MODE") == "true" else None
    try:
        version = importlib.metadata.version("fluidmcp")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"

    return TunnelClient(
        url=url,
        token=token,
        connector_id=connector_id,
        allowed_servers=allowed,
        server_public_keys=server_keys,
        identity_key=identity_key,
        local_base_url=f"http://127.0.0.1:{gateway_port}{os.environ.get('MCP_ROOT_PATH', '')}",
        local_token=local_token,
        max_concurrency=max_concurrency,
        request_timeout=request_timeout,
        version=version,
        host_override=host_override,
    )
