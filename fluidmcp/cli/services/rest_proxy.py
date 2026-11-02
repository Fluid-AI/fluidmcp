"""
REST proxy servers: a plain HTTP pass-through from /{name}/... to a configured target.

A REST proxy has no tools and does not speak JSON-RPC. Every request under
/{name}/ (any method) is forwarded to the target with its path, query string,
headers and body, and the upstream response is returned unchanged.

Config (one entry under restServers, or the body of POST /api/rest-servers):

    "restServers": {
      "gupshup-chat": {
        "type": "rest-proxy",
        "target-rest-endpoint": "media.gupshup.com"     # bare host means https://
      }
    }

    GET /gupshup-chat/wa/api/v1/msg?x=1  ->  GET https://media.gupshup.com/wa/api/v1/msg?x=1

In secure mode FluidMCP's own token goes in the FluidMCP-Authorization header,
so the caller's Authorization header can be forwarded to the upstream untouched.
Errors produced by FluidMCP itself (not the upstream) carry an X-FluidMCP-Error
header so callers can tell the two apart.
"""
import asyncio
import os
import re
import time
from typing import Any, AsyncIterator, Dict, Iterable, List, Mapping, Optional, Tuple
from urllib.parse import unquote, urlsplit, urlunsplit

import httpx
from fastapi import HTTPException
from loguru import logger
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import BaseRoute, Match, NoMatchFound
from starlette.types import Receive, Scope, Send

from ..auth import verify_proxy_token
from .metrics import MetricsCollector
from .package_launcher import _sanitize_log_field

REST_PROXY_TYPE = "rest-proxy"
TARGET_FIELD = "target-rest-endpoint"
ALLOWED_FIELDS = ("type", TARGET_FIELD)

ERROR_HEADER = "X-FluidMCP-Error"

# Same character set as URL path segments that need no escaping, so /{name}/ is
# always a literal match.
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

# First path segments already owned by fmcp run / fmcp serve. A REST proxy route
# is matched before every other route, so these names would hide those endpoints.
RESERVED_NAMES = frozenset({
    "api", "ui", "llm", "health", "metrics", "docs", "redoc", "openapi.json",
    "status", "servers", "documentation", "inspector",
})

# Hop-by-hop headers (RFC 9110 section 7.6.1) apply to one connection only and
# must not be forwarded. Host is set by the HTTP client from the target URL.
HOP_BY_HOP_HEADERS = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "proxy-connection", "te", "trailer", "transfer-encoding", "upgrade",
})
# Uvicorn always adds its own Date and Server headers to every response, so the
# upstream's copies are dropped rather than sent twice.
GATEWAY_RESPONSE_HEADERS = frozenset({"date", "server"})
FLUIDMCP_HEADER_PREFIX = b"fluidmcp-"

DEFAULT_TIMEOUT_SECONDS = 60.0
CONNECT_TIMEOUT_SECONDS = 10.0


def normalize_target(value: Any) -> str:
    """
    Return the canonical target URL for a target-rest-endpoint value.

    A bare host ("media.gupshup.com") means https. A base path is kept, a
    trailing slash is dropped. Raises ValueError if the value is unusable.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{TARGET_FIELD}' must be a non-empty string")
    value = value.strip()
    if any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError(f"Field '{TARGET_FIELD}' must not contain whitespace or control characters")
    if "://" not in value:
        value = "https://" + value

    parsed = urlsplit(value)
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"Field '{TARGET_FIELD}' must be an http:// or https:// URL or a bare host")
    if not parsed.hostname:
        raise ValueError(f"Field '{TARGET_FIELD}' must include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"Field '{TARGET_FIELD}' must not contain a username or password")
    if parsed.query or parsed.fragment or "?" in value or "#" in value:
        raise ValueError(f"Field '{TARGET_FIELD}' must not contain a query string or fragment")
    try:
        parsed.port
    except ValueError:
        raise ValueError(f"Field '{TARGET_FIELD}' has an invalid port")

    return urlunsplit((scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def validate_rest_server(name: Any, config: Any, mcp_server_names: Iterable[str] = ()) -> List[str]:
    """Return a list of problems with one restServers entry (empty if valid)."""
    errors = []
    label = f"REST server '{name}'"

    if not isinstance(name, str) or not NAME_PATTERN.match(name):
        errors.append(f"{label}: name must be 1-64 letters, digits, '_' or '-', starting with a letter or digit")
    elif name.lower() in RESERVED_NAMES:
        errors.append(f"{label}: name is reserved by FluidMCP ({', '.join(sorted(RESERVED_NAMES))})")
    elif name in set(mcp_server_names):
        errors.append(f"{label}: name is already used by an MCP server")

    if not isinstance(config, dict):
        errors.append(f"{label}: configuration must be an object")
        return errors

    if config.get("type") != REST_PROXY_TYPE:
        errors.append(f"{label}: field 'type' must be \"{REST_PROXY_TYPE}\"")
    unknown = sorted(set(config) - set(ALLOWED_FIELDS))
    if unknown:
        errors.append(
            f"{label}: unknown field(s) {', '.join(unknown)} "
            f"(a REST proxy takes only 'type' and '{TARGET_FIELD}')"
        )
    try:
        normalize_target(config.get(TARGET_FIELD))
    except ValueError as e:
        errors.append(f"{label}: {e}")

    return errors


def validate_rest_servers(rest_servers: Any, mcp_server_names: Iterable[str] = ()) -> List[str]:
    """Return a list of problems with a whole restServers section (empty if valid)."""
    if not isinstance(rest_servers, dict):
        return ["Field 'restServers' must be an object"]
    mcp_server_names = set(mcp_server_names)
    errors = []
    for name, config in rest_servers.items():
        errors.extend(validate_rest_server(name, config, mcp_server_names))
    return errors


class RestProxyRegistry:
    """REST proxy name -> normalized target URL. Changes take effect on the next request."""

    def __init__(self):
        self._targets: Dict[str, str] = {}

    def register(self, name: str, config: Mapping[str, Any]) -> str:
        """Validate and add (or replace) a REST proxy. Returns the normalized target."""
        errors = validate_rest_server(name, dict(config))
        if errors:
            raise ValueError("; ".join(errors))
        target = normalize_target(config[TARGET_FIELD])
        self._targets[name] = target
        return target

    def unregister(self, name: str) -> bool:
        return self._targets.pop(name, None) is not None

    def get(self, name: str) -> Optional[str]:
        return self._targets.get(name)

    def names(self) -> List[str]:
        return sorted(self._targets)

    def __contains__(self, name: object) -> bool:
        return name in self._targets

    def __len__(self) -> int:
        return len(self._targets)


# ── Shared upstream client ──────────────────────────────────────────────────

_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()


def _timeout_from_env() -> float:
    raw = os.environ.get("FMCP_REST_PROXY_TIMEOUT")
    if raw is None:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
        if value > 0:
            return value
    except ValueError:
        pass
    logger.warning(f"Invalid FMCP_REST_PROXY_TIMEOUT '{raw}', using {DEFAULT_TIMEOUT_SECONDS}s")
    return DEFAULT_TIMEOUT_SECONDS


def create_client() -> httpx.AsyncClient:
    """An upstream client that adds nothing to the caller's request and never follows redirects."""
    timeout = _timeout_from_env()
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=CONNECT_TIMEOUT_SECONDS),
        follow_redirects=False,
    )
    # httpx adds Accept, Accept-Encoding, Connection and User-Agent by default.
    # Clear them so the upstream sees only what the caller sent.
    client.headers.clear()
    return client


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        async with _client_lock:
            if _client is None:
                _client = create_client()
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ── Forwarding ──────────────────────────────────────────────────────────────

def _connection_listed(headers: Iterable[Tuple[bytes, bytes]]) -> set:
    """Header names listed in Connection, which are hop-by-hop for this message."""
    listed = set()
    for key, value in headers:
        if key.lower() == b"connection":
            listed.update(t.strip().lower() for t in value.decode("latin-1").split(",") if t.strip())
    return listed


def _filter_request_headers(raw_headers: List[Tuple[bytes, bytes]]) -> List[Tuple[bytes, bytes]]:
    drop = HOP_BY_HOP_HEADERS | {"host"} | _connection_listed(raw_headers)
    return [
        (key, value) for key, value in raw_headers
        if key.decode("latin-1").lower() not in drop and not key.lower().startswith(FLUIDMCP_HEADER_PREFIX)
    ]


def _filter_response_headers(raw_headers: List[Tuple[bytes, bytes]]) -> List[Tuple[bytes, bytes]]:
    drop = HOP_BY_HOP_HEADERS | GATEWAY_RESPONSE_HEADERS | _connection_listed(raw_headers)
    return [(key, value) for key, value in raw_headers if key.decode("latin-1").lower() not in drop]


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": code, "message": message}, status_code=status, headers={ERROR_HEADER: code})


def build_upstream_url(target: str, tail: bytes, query_string: bytes) -> httpx.URL:
    """
    Join the target with the request path after /{name} and the raw query string.

    tail is the raw (still percent-encoded) path after the proxy name: b"" or b"/...".
    Scheme, host and port always come from the target, never from the request.
    """
    target_url = httpx.URL(target)
    base = target_url.raw_path.split(b"?", 1)[0].rstrip(b"/")
    path = base + tail or b"/"
    if query_string:
        path += b"?" + query_string
    return target_url.copy_with(raw_path=path)


def _has_dot_segment(tail: bytes) -> bool:
    return any(unquote(seg.decode("latin-1")) in (".", "..") for seg in tail.split(b"/"))


async def _request_body(request: Request) -> AsyncIterator[bytes]:
    async for chunk in request.stream():
        if chunk:
            yield chunk


async def proxy_request(
    request: Request,
    name: str,
    target: str,
    tail: bytes,
    client: httpx.AsyncClient,
) -> Response:
    """Forward one request to the target and stream the upstream response back."""
    method = request.method
    log_path = _sanitize_log_field(unquote(tail.decode("latin-1")) or "/")
    log = logger.bind(server_id=f"rest:{name}")
    ctx = f"proxy={name} method={method} path={log_path}"

    try:
        verify_proxy_token(request)
    except HTTPException as e:
        log.warning(f"[rest.unauthorized] {ctx} status={e.status_code}")
        code = "unauthorized" if e.status_code == 401 else "misconfigured"
        return _error(e.status_code, code, str(e.detail))

    if _has_dot_segment(tail):
        log.warning(f"[rest.bad_path] {ctx}")
        return _error(400, "bad_path", "Path must not contain '.' or '..' segments")

    url = build_upstream_url(target, tail, request.scope.get("query_string", b""))
    headers = _filter_request_headers(list(request.headers.raw))
    has_body = "content-length" in request.headers or "transfer-encoding" in request.headers

    collector = MetricsCollector(f"rest:{name}")
    collector.increment_active_requests()
    t0 = time.monotonic()
    upstream = None
    try:
        upstream_request = client.build_request(
            method, url, headers=headers, content=_request_body(request) if has_body else None
        )
        upstream = await client.send(upstream_request, stream=True)
    except httpx.TimeoutException:
        elapsed = time.monotonic() - t0
        log.warning(f"[rest.timeout] {ctx} elapsed={int(elapsed * 1000)}ms")
        collector.record_request(method, "error", elapsed)
        collector.record_error("network_error")
        return _error(504, "upstream_timeout", "Upstream did not respond within the timeout")
    except httpx.HTTPError as e:
        elapsed = time.monotonic() - t0
        log.warning(f"[rest.unreachable] {ctx} error={type(e).__name__} elapsed={int(elapsed * 1000)}ms")
        collector.record_request(method, "error", elapsed)
        collector.record_error("network_error")
        return _error(502, "upstream_unreachable", f"Could not reach upstream: {type(e).__name__}")
    finally:
        if upstream is None:
            collector.decrement_active_requests()

    elapsed = time.monotonic() - t0
    log.info(f"[rest.ok] {ctx} status={upstream.status_code} elapsed={int(elapsed * 1000)}ms")
    collector.record_request(method, "success", elapsed)

    closed = False

    async def close() -> None:
        # Runs from the body's finally and again as the background task, so the
        # upstream connection is released even if the caller disconnects early.
        nonlocal closed
        if not closed:
            closed = True
            await upstream.aclose()
            collector.decrement_active_requests()

    async def body() -> AsyncIterator[bytes]:
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        except httpx.HTTPError as e:
            # Headers are already sent; all we can do is stop and log.
            log.warning(f"[rest.stream_error] {ctx} error={type(e).__name__}")
        finally:
            await close()

    response = StreamingResponse(body(), status_code=upstream.status_code, background=BackgroundTask(close))
    # Raw list keeps repeated headers such as Set-Cookie and the upstream's
    # Content-Length / Content-Encoding exactly as sent.
    response.raw_headers = _filter_response_headers(list(upstream.headers.raw))
    return response


class RestProxyRoute(BaseRoute):
    """
    Matches /{name}/... only when name is a registered REST proxy.

    Inserted ahead of every other route (install_rest_proxy), so /{name}/mcp on a
    REST proxy is forwarded instead of reaching the MCP router, while paths for
    unregistered names fall through to the normal routes untouched.
    """

    def __init__(self, registry: RestProxyRegistry, root_path: str = "", client: Optional[httpx.AsyncClient] = None):
        self.registry = registry
        self.root_path = root_path.rstrip("/")
        self._client = client

    def _split(self, path: str) -> Optional[str]:
        """Return the proxy name if path is /{root}/{name}[/...] for a registered name."""
        if self.root_path:
            if not path.startswith(self.root_path + "/"):
                return None
            path = path[len(self.root_path):]
        name = path[1:].split("/", 1)[0]
        return name if name in self.registry else None

    def matches(self, scope: Scope) -> Tuple[Match, Scope]:
        if scope["type"] != "http":
            return Match.NONE, {}
        name = self._split(scope["path"])
        if name is None:
            return Match.NONE, {}
        return Match.FULL, {"fluidmcp.rest_proxy": name}

    def url_path_for(self, name: str, /, **path_params: Any):
        raise NoMatchFound(name, path_params)

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        name = scope["fluidmcp.rest_proxy"]
        target = self.registry.get(name)
        request = Request(scope, receive)
        if target is None:
            # Removed between match and handle.
            response: Response = _error(404, "rest_server_not_found", f"REST server '{name}' not found")
        else:
            raw_path = scope.get("raw_path") or scope["path"].encode("utf-8")
            raw_path = raw_path.split(b"?", 1)[0]
            if self.root_path:
                raw_path = raw_path[len(self.root_path):]
            # Drop "/{name}" (raw form may be percent-encoded) and keep the rest.
            tail = raw_path[1:].partition(b"/")
            tail = (b"/" + tail[2]) if tail[1] else b""
            client = self._client or await get_client()
            response = await proxy_request(request, name, target, tail, client)
        await response(scope, receive, send)


async def load_rest_servers(persistence, registry: RestProxyRegistry) -> int:
    """
    Register every REST proxy stored in the persistence backend (fmcp serve startup).

    An entry that no longer validates is logged and skipped rather than
    stopping startup. Returns the number registered.
    """
    loaded = 0
    for doc in await persistence.list_rest_servers():
        name = doc.get("id")
        entry = {k: doc[k] for k in ALLOWED_FIELDS if k in doc}
        try:
            registry.register(name, entry)
            loaded += 1
        except ValueError as e:
            logger.error(f"Skipping stored REST server '{_sanitize_log_field(str(name))}': {e}")
    return loaded


def install_rest_proxy(app, registry: RestProxyRegistry, client: Optional[httpx.AsyncClient] = None) -> RestProxyRoute:
    """Put the REST proxy route ahead of every other route on the app."""
    route = RestProxyRoute(registry, root_path=os.environ.get("MCP_ROOT_PATH", ""), client=client)
    app.router.routes.insert(0, route)
    return route
