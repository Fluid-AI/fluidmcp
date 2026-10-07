import os
import json
import subprocess
import shutil
import asyncio
import time
import threading
from collections import deque
import uuid
import httpx
from typing import Union, Dict, Any, Iterator, AsyncIterator, Optional, Tuple
from pathlib import Path
from loguru import logger
from fastapi import Request, APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..utils.env_utils import is_placeholder
from .metrics import MetricsCollector, RequestTimer
from .network_handle import NetworkSubprocessHandle
from .sse_handle import SseSubprocessHandle
from .stdio_jsonrpc import StdioProcessClosed, StdioRequestTimeout, get_stdio_router

security = HTTPBearer(auto_error=False)


def _is_unfilled(v) -> bool:
    """Return True if the LLM left this parameter at its None default."""
    return v is None


def _sanitize_log_field(value: str, max_len: int = 200) -> str:
    """Strip CR/LF/control characters from user-controlled values before logging."""
    sanitized = "".join(ch for ch in str(value) if ch.isprintable() and ch not in "\r\n")
    return sanitized[:max_len]


# Max seconds to wait for an MCP subprocess to write a response line.
# Overridable via the MCP_READ_TIMEOUT environment variable.
_MCP_READ_TIMEOUT = float(os.environ.get("MCP_READ_TIMEOUT", "45"))


# Per-process stderr buffers: key -> (lock, deque of last 200 lines)
# Continuously drained by a daemon thread to prevent the 64 KB OS pipe
# buffer from filling up and silently freezing the subprocess.
_stderr_buffers: Dict[str, tuple] = {}  # key -> (threading.Lock, deque)


def start_stderr_drainer(process: subprocess.Popen, key: str, log_fh=None) -> None:
    """Start a daemon thread that continuously drains stderr for a subprocess.

    Without this, any MCP server that writes enough to stderr will fill the
    64 KB OS pipe buffer and freeze — stopping stdout communication too.
    The buffer stores the last 200 lines for crash diagnosis.

    Args:
        log_fh: Optional open file handle to mirror stderr lines into (in addition
                to the in-memory buffer and terminal logger).
    """
    lock = threading.Lock()
    buf: deque = deque(maxlen=200)
    _stderr_buffers[key] = (lock, buf)

    _bound = logger.bind(server_id=key)

    def _drain() -> None:
        nonlocal log_fh
        try:
            if process.stderr is None:
                return
            for line in process.stderr:
                stripped = line.rstrip()
                with lock:
                    buf.append(stripped)
                _bound.debug("[{}] {}", key, stripped)
                if log_fh:
                    try:
                        log_fh.write(line)
                        log_fh.flush()
                    except (OSError, ValueError):
                        # Permanent write failure (disk full, file deleted) — close and
                        # stop trying so the FD is not leaked for the process lifetime.
                        try:
                            log_fh.close()
                        except Exception:
                            pass
                        log_fh = None
        except (OSError, ValueError):
            pass  # Expected: pipe closed when process exits
        except Exception:
            logger.exception("[{}] Unexpected error in stderr drainer", key)

    t = threading.Thread(target=_drain, name=f"stderr-drainer-{key}", daemon=True)
    t.start()


def get_stderr_tail(key: str, lines: int = 50) -> str:
    """Return the last N stderr lines for a given key (for crash diagnosis)."""
    entry = _stderr_buffers.get(key)
    if not entry:
        return ""
    lock, buf = entry
    with lock:
        snapshot = list(buf)
    return "\n".join(snapshot[-lines:])


def clear_stderr_buffer(key: str) -> None:
    """Remove the stderr buffer for a server key to free memory after it stops."""
    _stderr_buffers.pop(key, None)


def find_metadata_file(base_dir: Path) -> Path:
    """
    Find metadata.json in repo.
    Supports both root-level and nested MCP structures.
    """
    # 1. Check root first
    root_meta = base_dir / "metadata.json"
    if root_meta.exists():
        try:
            with root_meta.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "mcpServers" in data:
                return root_meta
        except Exception:
            pass
    excluded_dirs = {
        "node_modules", ".git", ".hg", ".svn",
        "venv", ".venv", "__pycache__", ".mypy_cache"
    }

    # 2. Search inside repo (up to 2 levels deep)
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in excluded_dirs]
        # Determine depth relative to base_dir
        rel = Path(root).relative_to(base_dir)
        depth = len(rel.parts)
        # Stop descending beyond 2 levels
        if depth > 2:
            dirs[:] = []
            continue

        if "metadata.json" in files and depth > 0:
            return Path(root) / "metadata.json"

    raise FileNotFoundError(f"metadata.json not found in {base_dir}")

async def _proxy_to_sse_server(sse_url: str, payload: dict, timeout: float = 60.0, client=None) -> Optional[dict]:
    """Forward through an initialized MCP SSE session, restoring the caller ID."""
    from .sse_client import SseJsonRpcClient

    owned_client = client is None
    if owned_client:
        client = SseJsonRpcClient(sse_url)
    try:
        return await client.request(payload, timeout=timeout)
    except asyncio.TimeoutError:
        raise HTTPException(504, f"SSE server at {sse_url} timed out after {timeout}s")
    except (ConnectionError, httpx.ConnectError):
        raise HTTPException(503, f"Cannot reach SSE server at {sse_url}")
    except Exception as e:
        logger.error(f"SSE proxy error at {sse_url}: {e}")
        raise HTTPException(500, f"SSE proxy error: {str(e)}")
    finally:
        if owned_client:
            await client.aclose()

async def _proxy_to_http_server(
    base_url: str,
    payload: dict,
    timeout: float = 60.0,
    session_id: str = None,
    client: httpx.AsyncClient = None,
) -> Tuple[Optional[dict], Optional[str]]:
    """
    Forward a JSON-RPC request to a streamable-http MCP server via POST /mcp.

    Args:
        base_url:   Base URL of the HTTP server (e.g. "http://127.0.0.1:8000").
        payload:    JSON-RPC 2.0 dict to send.
        timeout:    HTTP request timeout in seconds.
        session_id: MCP session ID to include as mcp-session-id header.
        client:     Optional shared httpx.AsyncClient. When provided the pool's
                    pre-established connections are reused (no per-request TCP
                    handshake). When None a fresh short-lived client is created.

    Returns:
        (response, upstream_session_id) — response is the parsed JSON-RPC
        response dict, or None for a JSON-RPC *notification* (a payload with
        no "id"), since the spec defines no response body for those (servers
        typically ack with an empty 202). upstream_session_id is the
        Mcp-Session-Id header from this response, if the upstream sent one.

    Raises:
        HTTPException on any HTTP or connection error.
    """
    mcp_url = f"{base_url.rstrip('/')}/mcp"
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    # Stateful servers require every request to carry the session ID negotiated
    # during the initialize handshake. Stateless servers omit it entirely.
    if session_id:
        headers["mcp-session-id"] = session_id

    # A JSON-RPC notification (no "id") gets no JSON-RPC response by spec —
    # don't attempt to parse one, or an empty/non-JSON ack body raises here.
    is_notification = "id" not in payload
    # All downstream clients share the subprocess's upstream session. Preserve
    # their IDs only in this request's stack; never put a repeated client ID on
    # the upstream wire. Do not mutate the caller's request or add IDs to notifications.
    outgoing = payload if is_notification else {**payload, "id": uuid.uuid4().hex}

    def restore_response(message):
        if (not isinstance(message, dict) or message.get("jsonrpc") != "2.0"
                or message.get("id") != outgoing["id"]
                or ("result" in message) == ("error" in message)):
            raise HTTPException(502, "Upstream MCP response does not match the forwarded request")
        return {**message, "id": payload["id"]}

    # Use the caller-supplied shared pool when available. If not (e.g. tool
    # discovery at startup, or SSE fallback paths), create a short-lived client
    # and close it in the finally block so connections don't leak.
    owned_client = client is None
    if owned_client:
        client = httpx.AsyncClient(timeout=timeout)

    try:
        resp = await client.post(mcp_url, json=outgoing, headers=headers, timeout=timeout)
        resp.raise_for_status()
        upstream_session_id = resp.headers.get("mcp-session-id")

        if is_notification:
            return None, upstream_session_id

        # FastMCP returns text/event-stream even for non-streaming responses.
        # Unwrap the SSE envelope to get the plain JSON-RPC payload.
        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            from httpx_sse import EventSource

            for event in EventSource(resp).iter_sse():
                if not event.data:
                    continue
                message = json.loads(event.data)
                # Progress notifications/server requests are not the response.
                if isinstance(message, dict) and "method" in message:
                    continue
                return restore_response(message), upstream_session_id
            raise HTTPException(502, "Upstream MCP stream ended without a response")
        return restore_response(resp.json()), upstream_session_id
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            e.response.status_code,
            f"HTTP server returned HTTP {e.response.status_code}"
        )
    except httpx.ConnectError:
        raise HTTPException(
            503,
            f"Cannot reach HTTP server at {base_url}. Is it still running?"
        )
    except httpx.TimeoutException:
        raise HTTPException(
            504,
            f"HTTP server at {base_url} timed out after {timeout}s"
        )
    except Exception as e:
        logger.error(f"HTTP proxy error → {mcp_url}: {e}")
        raise HTTPException(500, f"HTTP proxy error: {str(e)}")
    finally:
        if owned_client:
            await client.aclose()

def get_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate bearer token if secure mode is enabled"""
    bearer_token = os.environ.get("FMCP_BEARER_TOKEN")
    secure_mode = os.environ.get("FMCP_SECURE_MODE") == "true"
    
    if not secure_mode:
        return None
    if not credentials or credentials.scheme.lower() != "bearer" or credentials.credentials != bearer_token:
        raise HTTPException(status_code=401, detail="Invalid or missing authorization token")
    return credentials.credentials

def launch_mcp_using_fastapi_proxy(dest_dir: Union[str, Path], process_lock: threading.Lock = None):
    """
    Launch an MCP server and create a FastAPI router for it.

    Args:
        dest_dir: Path to the package installation directory
        process_lock: Optional threading lock for process communication

    Returns:
        Tuple of (package_name, router, process) or (None, None, None) on failure
    """
    dest_dir = Path(dest_dir)
    

    try:
        metadata_path = find_metadata_file(dest_dir)
        
        logger.info(f"Reading metadata.json from {metadata_path}")
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        pkg = list(metadata["mcpServers"].keys())[0]
        servers = metadata['mcpServers'][pkg]
        logger.debug(f"Package: {pkg}, Servers: {servers}")
    except FileNotFoundError:
        logger.warning(f"No metadata.json found in {dest_dir}")
        return None, None, None
    except Exception:
        logger.exception("Error reading metadata.json")
        return None, None, None

    def replace_path_placeholders(arg: str, base_path: Path) -> str:
        """Replace common path placeholder patterns with actual directory"""
        placeholders = [
            "<path to mcp-servers>",
            "<path-to-your-directory>",
            "<path-to-directory>",
            "<installation-path>",
            "<package-dir>",
            "<package-directory>"
        ]
        result = arg
        for placeholder in placeholders:
            result = result.replace(placeholder, str(base_path))
        return result

    try:
        base_command = servers["command"]
        raw_args = servers["args"]

        # Resolve npm/npx paths
        if base_command == "npx" or base_command == "npm":
            npm_path = shutil.which("npm")
            npx_path = shutil.which("npx")
            if npm_path and base_command == "npm":
                base_command = npm_path
            elif npx_path and base_command == "npx":
                base_command = npx_path

        logger.debug(f"Raw args from metadata: {raw_args}")
        args = [replace_path_placeholders(arg, dest_dir) for arg in raw_args]
        logger.debug(f"Resolved args after placeholder replacement: {args}")
        stdio_command = [base_command] + args
        env_vars = servers.get("env", {})

        # Start with shell environment variables (these take precedence)
        env = dict(os.environ)

        # Add metadata.json env vars, but skip placeholders
        # Shell env vars take precedence (won't be overwritten)
        placeholders_found = []
        for key, value in env_vars.items():
            if key not in env:  # Only add if not already in shell env
                if is_placeholder(value):
                    placeholders_found.append((key, value))
                    logger.warning(
                        f"Skipping placeholder value for {key}='{value}'. "
                        f"Set this environment variable or use 'fmcp edit-env' to configure."
                    )
                else:
                    env[key] = value
            else:
                logger.debug(f"Using shell environment value for {key} (metadata.json value ignored)")

        # Log summary if placeholders were found
        if placeholders_found:
            logger.warning(
                f"Found {len(placeholders_found)} placeholder environment variable(s). "
                f"Server may fail to start. Use 'fmcp edit-env {pkg}' to configure: "
                f"{', '.join([k for k, v in placeholders_found])}"
            )

        # Simple and predictable: run from metadata location
        working_dir = metadata_path.parent
        logger.info(f"Using working directory: {working_dir}")
        
        process = subprocess.Popen(
            stdio_command,
            cwd=working_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,  # ensure stdin/stdout is in text mode
            bufsize=1
        )
        # Drain stderr continuously so the 64 KB pipe buffer never fills
        start_stderr_drainer(process, pkg)

        # Initialize MCP server — if this fails the process is dead/unusable,
        # kill it and return None so the caller skips registering a broken router.
        if not initialize_mcp_server(process, stderr_key=pkg):
            error_msg = f"Failed to initialize MCP server for {pkg}"
            if placeholders_found:
                error_msg += (
                    f"\n\nPossible cause: {len(placeholders_found)} placeholder environment variable(s) detected."
                    f"\nPlease configure: {', '.join([k for k, v in placeholders_found])}"
                    f"\n\nTo fix: fmcp edit-env {pkg}"
                )
            logger.error(error_msg)
            stderr_tail = get_stderr_tail(pkg, 20)
            if stderr_tail:
                logger.error(f"[{pkg}] stderr:\n{stderr_tail}")
            process.kill()
            clear_stderr_buffer(pkg)
            return None, None, None

        logger.debug(f"Launched MCP server process for package: {pkg}")
        return pkg, None, process  # router is None — callers use create_dynamic_router(server_manager)

    except FileNotFoundError:
        logger.exception("Command not found")
        return None, None, None
    except Exception:
        logger.exception("Error launching MCP server")
        return None, None, None
    



def initialize_mcp_server(process: subprocess.Popen, timeout: int = 30, stderr_key: str = "") -> bool:
    """
    Initialize MCP server with proper handshake.

    Args:
        process: Subprocess.Popen instance
        timeout: Timeout in seconds (default: 30, increased for npx -y downloads)
        stderr_key: Key used by start_stderr_drainer for crash log lookup

    Returns:
        True if initialization successful
    """
    try:
        # Check if process is already dead
        if process.poll() is not None:
            stderr_output = get_stderr_tail(stderr_key, 50) or "No stderr available"
            logger.error(f"Process died before initialization. stderr: {stderr_output}")
            return False

        # Send initialize request
        init_request = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"roots": {"listChanged": True}, "sampling": {}},
                "clientInfo": {"name": "fluidmcp-client", "version": "2.0.0"}
            }
        }

        # From here on the StdioJsonRpcRouter is the only reader of this process's
        # stdout. It skips non-JSON log lines and matches the response by ID.
        router = get_stdio_router(process, stderr_key)
        logger.debug("Sending initialize request")
        try:
            response = router.request_sync(init_request, timeout=timeout)
        except (BrokenPipeError, OSError) as e:
            logger.error(f"Failed to write initialize request (process likely died): {e}")
            return False
        except StdioRequestTimeout:
            logger.error(f"MCP initialization timeout after {timeout} seconds")
            non_json = router.stats["non_json_lines"]
            if non_json:
                logger.error(f"Received {non_json} non-JSON stdout line(s) and no initialize response")
            else:
                logger.error("No initialize response received from MCP server")
            stderr_output = get_stderr_tail(stderr_key, 50)
            if stderr_output:
                logger.error(f"Process stderr: {stderr_output}")
            return False
        except StdioProcessClosed as e:
            stderr_output = get_stderr_tail(stderr_key, 50) or "No stderr available"
            logger.error(f"Process died during initialization ({e}). stderr: {stderr_output}")
            return False

        if "result" not in response:
            logger.error(f"MCP initialize returned an error: {str(response.get('error'))[:300]}")
            return False

        try:
            router.notify({"jsonrpc": "2.0", "method": "notifications/initialized"})
        except (BrokenPipeError, OSError, StdioProcessClosed) as e:
            logger.error(f"Failed to send initialized notification: {e}")
            return False

        non_json = router.stats["non_json_lines"]
        if non_json:
            logger.info(f"MCP server initialized successfully (skipped {non_json} non-JSON log lines)")
        else:
            logger.info("MCP server initialized successfully")
        return True
    except Exception:
        logger.exception("Initialization error")
        return False
    

def create_dynamic_router(server_manager):
    """
    Create a dynamic router that dispatches MCP requests to running servers.

    Instead of creating separate routers per server, this creates a single
    router that dispatches based on server_name path parameter.

    Args:
        server_manager: ServerManager instance

    Returns:
        APIRouter with dynamic dispatch endpoints
    """
    router = APIRouter()
    # Note: stdio I/O safety is provided by the per-process StdioJsonRpcRouter
    # (stdio_jsonrpc.py), which replaces the previous per-server asyncio I/O lock.
    # That lock serialized write+read so a reader got "the next line", but it only
    # covered this router (not management/tool discovery) and could not stop a
    # timed-out request's late response from being read by the next request.
    # The router keeps its guarantee — atomic, non-interleaved stdin writes — via
    # its own write lock shared by every caller, and adds ID-based response routing.

    async def auto_start_stopped_server(server_name: str) -> None:
        """
        Auto-start a stopped/idle-cleaned server if it has a valid, enabled config in the DB.

        Raises HTTPException 404 if no config exists or server is disabled.
        Raises HTTPException 503 if auto-start fails.
        Does nothing if the server is already running.
        """
        # Fast path: process is alive, nothing to do
        process = server_manager.processes.get(server_name)
        if process is not None and process.poll() is None:
            return

        # No running process — check DB for a valid, enabled config
        if server_manager.db is None:
            raise HTTPException(404, f"Server '{server_name}' not found or not running")

        config = await server_manager.db.get_server_config(server_name)
        if not config or config.get("deleted_at"):
            raise HTTPException(404, f"Server '{server_name}' not found or not running")
        if not config.get("enabled", True):
            raise HTTPException(404, f"Server '{server_name}' is disabled")

        safe_name = server_name.replace('\n', '\\n').replace('\r', '\\r')
        logger.info(f"Auto-starting server '{safe_name}' on demand")
        # Pass config so start_server skips a redundant DB fetch
        started = await server_manager.start_server(server_name, config=config)
        if not started:
            raise HTTPException(503, f"Server '{server_name}' failed to auto-start")

    @router.post("/{server_name}/mcp", tags=["mcp"])
    async def proxy_jsonrpc(
        server_name: str,
        request: Dict[str, Any] = Body(
            ...,
            example={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {}
            }
        ),
        token: str = Depends(get_token)
    ):
        """
        Dynamic proxy for the server-manager mode (fmcp serve).
        Dispatches JSON-RPC requests to named running MCP subprocesses.

        Error map (what you'll see in logs → root cause):
          [mcp.not_found]      WARN  — server_name not in server_manager.processes.
                                       Root cause: server was never started, failed to start,
                                       or was stopped/evicted by the idle-timeout cleanup.
                                       Check [mcp.process_dead] or startup logs.
          [mcp.process_dead]   ERROR — process.poll() returned non-None before the request.
                                       Root cause: subprocess exited between the last request
                                       and this one. returncode and stderr tail are included.
                                       Common causes: OOM, unhandled top-level exception,
                                       external SIGKILL.
          [mcp.call]           INFO  — request accepted and about to be forwarded.
          [mcp.ok]             INFO  — successful response; elapsed time included.
          [mcp.slow]           WARN  — successful but took >5s. Not an error yet, but worth
                                       investigating the downstream tool or API.
          [mcp.timeout]        WARN  — subprocess alive but no stdout within 30s.
                                       Root cause: tool blocked (DB query, HTTP call, etc.).
          [mcp.process_died]   ERROR — BrokenPipeError on stdin write.
                                       Root cause: subprocess crashed during this request.
                                       stderr tail is attached to the log line.
          [stdio.non_json]     DEBUG — stdout line is not valid JSON; skipped by the
                                       stdio router (never returned as a response).
                                       Root cause: tool wrote plain text/traceback to stdout.
          [stdio.orphan_response] WARN — response whose ID has no waiter (e.g. arrived after
                                       [mcp.timeout]); dropped, never given to another request.
          [mcp.error_response] WARN  — JSON-RPC error in response body.
                                       Tool is alive but the operation failed. Error code guide:
                                         -32603 Internal error → DB down, API 5xx, unhandled exception
                                         -32602 Invalid params → wrong argument types/missing args
                                         -32601 Method not found → wrong tool name
          [mcp.error]          ERROR — unexpected exception (asyncio cancel, MemoryError, etc.).
        """
        collector = MetricsCollector(server_name)
        method = _sanitize_log_field(request.get("method", "unknown"))

        # RequestTimer automatically records error_type="network_error" for HTTPExceptions
        # via RequestTimer.__exit__ → _categorize_error() → name-based matching.
        params = request.get("params", {})
        tool_name = _sanitize_log_field(params.get("name", "")) if method == "tools/call" else None
        _tool_args = params.get("arguments", {}) if method == "tools/call" else {}
        # Sanitize argument keys before logging — values are never logged, only key names.
        tool_args_set = sorted(_sanitize_log_field(k) for k, v in _tool_args.items() if not _is_unfilled(v))
        tool_args_empty = sorted(_sanitize_log_field(k) for k, v in _tool_args.items() if _is_unfilled(v))
        request_id = _sanitize_log_field(str(request.get("id", "-")))

        ctx = f"server={server_name} method={method} req_id={request_id}"
        if tool_name:
            ctx += f" tool={tool_name} args_set={tool_args_set} args_empty={tool_args_empty}"

        t0 = time.monotonic()

        # Bind server_id and trace_id into loguru context so every log line
        # for this request carries them in the JSON output — enables
        # `docker logs fluidmcp | grep '"server_id":"airbnb"'` to isolate one server.
        http_req = locals().get("http_request")
        trace_id = getattr(getattr(http_req, "state", None), "trace_id", "") if http_req else ""
        _log = logger.bind(server_id=server_name, trace_id=trace_id)

        with RequestTimer(collector, method):
            # CAUGHT: [mcp.not_found] — auto_start_stopped_server raises 404 when the
            # server was never started, has no config, or is disabled. It also covers
            # HEAD's plain "not registered" case: if idle-timeout evicted the process but
            # a valid enabled config still exists, it transparently restarts it instead
            # of failing the request.
            await auto_start_stopped_server(server_name)

            process = server_manager.processes.get(server_name)
            if process is None:
                raise HTTPException(503, f"Server '{server_name}' failed to start")

            # CAUGHT: [mcp.process_dead] — process exited before this request arrived.
            # Attaches stderr tail so you can see the crash reason without digging through files.
            # (SSE/Network handles are excluded here — their liveness is verified by the
            # HTTP call made in their own transport branch below.)
            if not isinstance(process, (SseSubprocessHandle, NetworkSubprocessHandle)) and process.poll() is not None:
                stderr_tail = get_stderr_tail(server_name, 20)
                _log.error(
                    f"[mcp.process_dead] {ctx} — process exited (returncode={process.returncode})"
                    + (f"\nstderr:\n{stderr_tail}" if stderr_tail else "")
                )
                raise HTTPException(503, f"Server '{server_name}' is not running (process died)")

            # The subprocess is already initialized at startup by initialize_mcp_server().
            # Forwarding initialize again would cause readline() to block forever (deadlock).
            # Handle these at the gateway level and never forward to the subprocess.
            if method == "initialize":
                return JSONResponse(
                    content={
                        "jsonrpc": "2.0",
                        "id": request.get("id", 0),
                        "result": {
                            "protocolVersion": request.get("params", {}).get("protocolVersion", "2025-03-26"),
                            "capabilities": {"experimental": {}, "prompts": {"listChanged": False}, "resources": {"subscribe": False, "listChanged": False}, "tools": {"listChanged": False}},
                            "serverInfo": {"name": server_name, "version": "1.0.0"}
                        }
                    },
                    headers={"mcp-session-id": str(uuid.uuid4())}
                )
            if method == "notifications/initialized":
                return Response(status_code=204)

            # LOGGED: [mcp.call] — last log before entering blocking I/O.
            # If you see [mcp.call] with no follow-up, the request is in-flight.
            _log.info(f"[mcp.call] {ctx}")

            # Concurrency limiting — wraps ALL transport paths (network, SSE, stdio).
            # sem._value peek is safe in asyncio: no await between check and acquire,
            # so no other coroutine can interleave and take the slot.
            sem = server_manager.get_concurrency_semaphore(server_name)
            if sem is not None:
                if sem._value <= 0:
                    collector.record_rejected_request("concurrency_limit")
                    return Response(
                        content='{"error":"too many concurrent requests"}',
                        status_code=429,
                        media_type="application/json",
                        headers={"Retry-After": "1"},
                    )
                await sem.acquire()

            try:
                # ── Network transport: forward via HTTP ──────────────────────────
                if isinstance(process, NetworkSubprocessHandle):
                    upstream_session_id = None
                    if process.transport == "http":
                        try:
                            _http_timeout = float(os.environ.get("FMCP_HTTP_PROXY_TIMEOUT", "60"))
                            response, upstream_session_id = await _proxy_to_http_server(process.base_url, request, timeout=_http_timeout, session_id=process.session_id, client=process.http_client)
                        except HTTPException as exc:
                            if exc.status_code == 504:
                                monitor = getattr(server_manager, "_health_monitor", None)
                                if monitor is not None:
                                    logger.error(
                                        f"[RESTART] '{server_name}' — 504 from subprocess, "
                                        f"scheduling immediate restart"
                                    )
                                    asyncio.ensure_future(monitor.trigger_restart(server_name))
                                else:
                                    logger.error(
                                        f"[RESTART] '{server_name}' — 504 from subprocess but "
                                        f"health monitor not available, server will not auto-restart"
                                    )
                            raise
                    else:
                        response = await _proxy_to_sse_server(process.base_url, request, client=process.sse_client)
                    elapsed_ms = int((time.monotonic() - t0) * 1000)
                    _log.info(f"[mcp.ok] {ctx} elapsed={elapsed_ms}ms transport={process.transport}")
                    response_headers = {"Mcp-Session-Id": upstream_session_id} if upstream_session_id else None
                    if response is None:
                        # JSON-RPC notification (e.g. notifications/initialized) — the
                        # spec defines no response body for these; ack with empty 202.
                        return Response(status_code=202, headers=response_headers)
                    return JSONResponse(content=response, headers=response_headers)

                # ── SSE transport: server is an HTTP-based SSE subprocess, not a stdio process.
                # Forward the request over HTTP instead of stdin/stdout.
                if isinstance(process, SseSubprocessHandle):
                    with RequestTimer(collector, request.get("method", "unknown")):
                        response = await _proxy_to_sse_server(process.sse_url, request)
                        elapsed_ms = int((time.monotonic() - t0) * 1000)
                        _log.info(f"[mcp.ok] {ctx} elapsed={elapsed_ms}ms transport=sse_http")
                        if response is None:
                            return Response(status_code=202)
                        return JSONResponse(content=response)

                # ── stdio transport: write to stdin, response routed by JSON-RPC ID ──
                # The per-process StdioJsonRpcRouter owns stdout (one reader thread) and
                # serializes stdin writes. Requests are NOT serialized: each gets a
                # gateway-unique ID and receives only the response carrying that ID, so
                # out-of-order responses and late responses after a timeout can never be
                # handed to the wrong caller.
                try:
                    rpc = get_stdio_router(process, server_name)

                    if "id" not in request:
                        # Client notification (e.g. notifications/cancelled): nothing to wait
                        # for. Waiting here would previously steal another request's response.
                        try:
                            rpc.notify(request)
                        except (BrokenPipeError, OSError, StdioProcessClosed) as e:
                            raise HTTPException(503, f"Server '{server_name}' process pipe broken: {str(e)}")
                        return Response(status_code=202)

                    try:
                        response_data = await rpc.request(request, timeout=_MCP_READ_TIMEOUT)
                    except (BrokenPipeError, OSError, StdioProcessClosed) as e:
                        # CAUGHT: [mcp.process_died] — stdin write failed or stdout closed
                        # mid-request. Root cause: subprocess crashed during this request.
                        # Attaches stderr tail for crash diagnosis.
                        elapsed_ms = int((time.monotonic() - t0) * 1000)
                        stderr_tail = get_stderr_tail(server_name, 20)
                        _log.error(
                            f"[mcp.process_died] {ctx} elapsed={elapsed_ms}ms — {type(e).__name__}: {e}"
                            + (f"\nstderr:\n{stderr_tail}" if stderr_tail else "")
                        )
                        raise HTTPException(503, f"Server '{server_name}' process pipe broken: {str(e)}")
                    except StdioRequestTimeout:
                        # CAUGHT: [mcp.timeout] — subprocess alive but produced no response
                        # with this request's ID in time. The waiter is removed, so a late
                        # response is dropped rather than returned to the next request.
                        # Common causes:
                        #   • DB connection with no query timeout (hangs indefinitely on refusal)
                        #   • HTTP call to an API with no timeout set
                        #   • Tool waiting on a lock or resource held by another process
                        elapsed_ms = int((time.monotonic() - t0) * 1000)
                        _log.warning(f"[mcp.timeout] {ctx} elapsed={elapsed_ms}ms — server did not respond within {_MCP_READ_TIMEOUT}s")
                        raise HTTPException(504, f"Server '{server_name}' did not respond within {_MCP_READ_TIMEOUT} seconds")
                    elapsed_ms = int((time.monotonic() - t0) * 1000)

                    # LOGGED: [mcp.slow] — response arrived but took longer than threshold.
                    # Not an error but a leading indicator that the downstream is degraded.
                    # Configure via FMCP_SLOW_REQUEST_MS (default: 5000).
                    _slow_ms = int(os.getenv("FMCP_SLOW_REQUEST_MS", "5000"))
                    if elapsed_ms > _slow_ms:
                        _log.warning(f"[mcp.slow] {ctx} elapsed={elapsed_ms}ms — response was slow")

                    if "error" in response_data:
                        # CAUGHT: [mcp.error_response] — tool ran but returned a JSON-RPC error.
                        # Tool is alive; this is an application-level failure, not a gateway failure.
                        # Error code guide:
                        #   -32603 Internal error  → unhandled exception in the tool
                        #                            (DB refused connection, API 5xx, file missing, etc.)
                        #   -32602 Invalid params  → wrong argument types or missing required args
                        #   -32601 Method not found → tool name doesn't exist on this server
                        #   -32700 Parse error     → gateway sent malformed JSON (should not happen)
                        err = response_data["error"]
                        err_code = err.get("code") if isinstance(err, dict) else None
                        err_msg = _sanitize_log_field(err.get("message") if isinstance(err, dict) else str(err))
                        _log.warning(f"[mcp.error_response] {ctx} elapsed={elapsed_ms}ms — code={err_code} message={err_msg}")
                    else:
                        _log.info(f"[mcp.ok] {ctx} elapsed={elapsed_ms}ms")

                    # Update last_used_at so the idle-timeout cleanup doesn't evict this server.
                    await server_manager.update_last_used(server_name)

                    return JSONResponse(content=response_data)

                except HTTPException:
                    raise
                except Exception as e:
                    # CAUGHT: [mcp.error] — unexpected exception not covered above.
                    # Could be asyncio.CancelledError (client disconnected mid-request),
                    # MemoryError, or a bug in gateway code. Full traceback is included.
                    elapsed_ms = int((time.monotonic() - t0) * 1000)
                    _log.error(f"[mcp.error] {ctx} elapsed={elapsed_ms}ms — {type(e).__name__}: {e}", exc_info=True)
                    raise HTTPException(500, f"Error communicating with server: {str(e)}")
            finally:
                if sem is not None:
                    sem.release()

    @router.post("/{server_name}/sse", tags=["mcp"])
    async def sse_stream(
        server_name: str,
        request: Dict[str, Any] = Body(...),
        token: str = Depends(get_token)
    ):
        """
        Server-Sent Events streaming endpoint for long-running MCP operations.
        """
        # Initialize metrics collector
        collector = MetricsCollector(server_name)

        # Pre-validation (errors NOT tracked - occurs before streaming begins)
        #
        # Design Decision: These HTTPExceptions (404/503) are intentionally NOT wrapped
        # in RequestTimer because they represent pre-flight validation failures that occur
        # before any MCP protocol interaction begins. They are pure HTTP-layer errors.
        # auto_start_stopped_server may auto-start a stopped server here; if it raises,
        # the error is still a pre-flight failure before any streaming begins.
        #
        # These errors are observable through:
        # 1. FastAPI's built-in HTTP error logs
        # 2. HTTP status code monitoring at the load balancer/proxy level
        # 3. Application logs (logged by FastAPI middleware)
        #
        # If you need metrics for these specific errors, consider:
        # - Option 1: New metric fluidmcp_http_errors_total{endpoint, status_code}
        # - Option 2: Manual tracking via collector.record_error("server_not_found")
        # - Option 3: Wrap these checks in a lightweight context manager
        #
        # Current implementation prioritizes clarity by separating HTTP validation from
        # MCP protocol errors tracked via RequestTimer.
        await auto_start_stopped_server(server_name)

        # Update last_used_at for idle cleanup when SSE connection is opened
        await server_manager.update_last_used(server_name)

        process = server_manager.processes.get(server_name)
        if process is None:
            raise HTTPException(503, f"Server '{server_name}' failed to start")

        # Concurrency limiting for SSE — long-lived connections consume a slot for their duration
        _sse_sem = server_manager.get_concurrency_semaphore(server_name)
        if _sse_sem is not None:
            # sem._value peek is safe in asyncio: no await between check and acquire
            if _sse_sem._value <= 0:
                collector.record_rejected_request("concurrency_limit")
                return Response(
                    content='{"error":"too many concurrent requests"}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": "1"},
                )
            await _sse_sem.acquire()

        # SSE error map for this path (server_manager mode):
        #   [mcp.sse.start]          INFO  — connection open, stdin write about to happen.
        #   [mcp.sse.chunk]          DEBUG — each chunk forwarded from subprocess stdout.
        #   [mcp.sse.keepalive]      DEBUG — 30s readline timeout with process still alive;
        #                                    a keep-alive comment is sent to hold the connection.
        #                                    Repeated keepalives mean the tool is running slowly.
        #   [mcp.sse.process_exited] ERROR — readline returned "" and process.poll() is set.
        #                                    Root cause: subprocess crashed mid-stream.
        #                                    returncode and stderr tail are attached.
        #   [mcp.sse.error_response] WARN  — tool sent a JSON-RPC error chunk in the stream.
        #                                    Root cause: same as [mcp.error_response] above.
        #   [mcp.sse.non_json]       DEBUG — non-JSON line received; silently forwarded.
        #                                    Some tools stream progress text before the final result.
        #   [mcp.sse.ok]             INFO  — "result" chunk received; stream completed normally.
        #   sse_proxy_error (metric) — httpx error when forwarding to SseSubprocessHandle.
        #                              Root cause: the external SSE HTTP server is unreachable
        #                              or returned an HTTP error (connect timeout, 5xx, etc.).
        #   [mcp.sse.error]          ERROR — unexpected exception in the generator.
        async def event_generator() -> AsyncIterator[str]:
            completion_status = "success"
            try:
                collector.increment_active_streams()

                # ── Network transport: forward to external HTTP server ───────
                if isinstance(process, (NetworkSubprocessHandle, SseSubprocessHandle)):
                    try:
                        if isinstance(process, NetworkSubprocessHandle) and process.transport == "http":
                            response, _ = await _proxy_to_http_server(
                                process.base_url, request, session_id=process.session_id,
                                client=process.http_client,
                            )
                        else:
                            base_url = process.base_url if isinstance(process, NetworkSubprocessHandle) else process.sse_url
                            response = await _proxy_to_sse_server(
                                base_url, request, client=getattr(process, "sse_client", None),
                            )
                        if response is not None:
                            yield f"data: {json.dumps(response)}\n\n"
                    except Exception as e:
                        completion_status = "error"
                        error_type = ("http_proxy_error" if isinstance(process, NetworkSubprocessHandle)
                                      and process.transport == "http" else "sse_proxy_error")
                        collector.record_error(error_type)
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    return

                # ── stdio transport continues below ──────────────────────────

                sse_method = _sanitize_log_field(request.get("method", "unknown"))
                sse_params = request.get("params", {})
                sse_tool_name = _sanitize_log_field(sse_params.get("name", "")) if sse_method == "tools/call" else None
                _sse_tool_args = sse_params.get("arguments", {}) if sse_method == "tools/call" else {}
                sse_args_set = sorted(_sanitize_log_field(k) for k, v in _sse_tool_args.items() if not _is_unfilled(v))
                sse_args_empty = sorted(_sanitize_log_field(k) for k, v in _sse_tool_args.items() if _is_unfilled(v))
                sse_ctx = f"server={server_name} method={sse_method} req_id={_sanitize_log_field(str(request.get('id', '-')))}"
                if sse_tool_name:
                    sse_ctx += f" tool={sse_tool_name} args_set={sse_args_set} args_empty={sse_args_empty}"
                t0_sse = time.monotonic()
                chunk_count = 0

                rpc = get_stdio_router(process, server_name)
                if "id" not in request:
                    # Client notification: forward it; there is no response to stream.
                    try:
                        rpc.notify(request)
                        # Not a completed request/response stream — label it separately so
                        # notification forwards don't inflate completion_status="success".
                        completion_status = "notification"
                    except (BrokenPipeError, OSError, StdioProcessClosed) as e:
                        completion_status = "broken_pipe"
                        collector.record_error("io_error")
                        logger.error(f"[mcp.sse.process_died] {sse_ctx} — broken pipe on notification: {e}")
                        yield f"data: {json.dumps({'error': f'Process pipe broken: {str(e)}'})}\n\n"
                    return

                # Progress notifications for this request (matched by its progressToken)
                # and the final response (matched by JSON-RPC ID) arrive on this queue.
                loop = asyncio.get_running_loop()
                events: asyncio.Queue = asyncio.Queue()

                def _on_progress(notification: Dict[str, Any]) -> None:
                    loop.call_soon_threadsafe(events.put_nowait, ("notification", notification))

                try:
                    # start() registers the waiter and writes to stdin synchronously, so
                    # any write failure is raised here rather than inside the wait task.
                    pending = rpc.start(request, on_notification=_on_progress)
                except (BrokenPipeError, OSError, StdioProcessClosed) as e:
                    # Set streaming-specific completion_status label (tracks how the SSE stream ended).
                    #
                    # IMPORTANT: This intentionally differs from the error_type used in
                    # fluidmcp_errors_total, where BrokenPipeError is grouped under "io_error".
                    # Here we use "broken_pipe" so operators can:
                    #   - Use fluidmcp_errors_total{error_type="io_error", ...} to monitor the
                    #     overall rate of I/O-related failures across the service, and
                    #   - Use streaming metrics with completion_status="broken_pipe" to understand
                    #     why individual streaming sessions terminated (client disconnects,
                    #     broken pipes, etc.).
                    #
                    # In other words, both labels refer to the same underlying condition but are
                    # scoped for different troubleshooting workflows: global error rates versus
                    # per-stream termination reasons.
                    elapsed_ms = int((time.monotonic() - t0_sse) * 1000)
                    completion_status = "broken_pipe"
                    collector.record_error("io_error")
                    logger.error(f"[mcp.sse.process_died] {sse_ctx} elapsed={elapsed_ms}ms — broken pipe: {e}")
                    yield f"data: {json.dumps({'error': f'Process pipe broken: {str(e)}'})}\n\n"
                    return

                # LOGGED: [mcp.sse.start] — stdin write succeeded; reading loop begins.
                logger.info(f"[mcp.sse.start] {sse_ctx}")

                rpc_task = asyncio.ensure_future(pending.wait(timeout=None))
                rpc_task.add_done_callback(lambda _t: events.put_nowait(("done", None)))
                try:
                    while True:
                        try:
                            kind, payload = await asyncio.wait_for(events.get(), _MCP_READ_TIMEOUT)
                        except asyncio.TimeoutError:
                            # Process is alive but produced nothing within the timeout — send a
                            # keep-alive SSE comment to prevent the client from closing the
                            # connection rather than aborting the stream outright.
                            # LOGGED: [mcp.sse.keepalive] DEBUG — expected for slow-running tools.
                            elapsed_ms = int((time.monotonic() - t0_sse) * 1000)
                            logger.debug(f"[mcp.sse.keepalive] {sse_ctx} elapsed={elapsed_ms}ms")
                            yield ": keep-alive\n\n"
                            continue

                        if kind == "notification":
                            chunk_count += 1
                            # LOGGED: [mcp.sse.chunk] DEBUG — progress notification for this request.
                            logger.debug(f"[mcp.sse.chunk] {sse_ctx} chunk={chunk_count} method={_sanitize_log_field(payload.get('method', ''))}")
                            yield f"data: {json.dumps(payload)}\n\n"
                            continue

                        # kind == "done": the response for this request's ID (or a failure).
                        try:
                            response_data = rpc_task.result()
                        except StdioProcessClosed as e:
                            # CAUGHT: [mcp.sse.process_exited] — subprocess exited mid-stream.
                            # process.returncode tells you how it died; stderr tail shows why.
                            elapsed_ms = int((time.monotonic() - t0_sse) * 1000)
                            completion_status = "error"
                            stderr_tail = get_stderr_tail(server_name, 20)
                            logger.error(
                                f"[mcp.sse.process_exited] {sse_ctx} elapsed={elapsed_ms}ms chunks={chunk_count} returncode={process.poll()}"
                                + (f"\nstderr:\n{stderr_tail}" if stderr_tail else "")
                            )
                            yield f"data: {json.dumps({'error': f'Process exited: {str(e)}'})}\n\n"
                            break

                        chunk_count += 1
                        elapsed_ms = int((time.monotonic() - t0_sse) * 1000)
                        yield f"data: {json.dumps(response_data)}\n\n"
                        if "error" in response_data:
                            # CAUGHT: [mcp.sse.error_response] — tool returned a JSON-RPC error.
                            # Root cause: same as [mcp.error_response] on the /mcp endpoint.
                            err = response_data["error"]
                            err_code = err.get("code") if isinstance(err, dict) else None
                            err_msg = _sanitize_log_field(err.get("message") if isinstance(err, dict) else str(err))
                            logger.warning(f"[mcp.sse.error_response] {sse_ctx} elapsed={elapsed_ms}ms code={err_code} message={err_msg}")
                            completion_status = "error_response"
                        else:
                            # LOGGED: [mcp.sse.ok] — tool completed normally.
                            completion_status = "success"
                            logger.info(f"[mcp.sse.ok] {sse_ctx} elapsed={elapsed_ms}ms chunks={chunk_count}")
                        break
                finally:
                    # Client disconnect / generator close: drop the waiter so a late
                    # response is discarded instead of reaching another request.
                    if not rpc_task.done():
                        rpc_task.cancel()

            except Exception as e:
                # CAUGHT: [mcp.sse.error] — unexpected exception in the generator.
                # Could be asyncio.CancelledError (client disconnected), MemoryError,
                # or a bug in gateway code. Full traceback is included.
                elapsed_ms = int((time.monotonic() - t0_sse) * 1000)
                completion_status = "error"
                logger.error(f"[mcp.sse.error] {sse_ctx} elapsed={elapsed_ms}ms — {type(e).__name__}: {e}", exc_info=True)
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                collector.record_streaming_request(completion_status)
                collector.decrement_active_streams()
                if _sse_sem is not None:
                    _sse_sem.release()

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )

    @router.get("/{server_name}/mcp/tools/list", tags=["mcp"])
    async def list_tools(
        server_name: str,
        token: str = Depends(get_token)
    ):
        """
        List available tools for a server.
        """
        await auto_start_stopped_server(server_name)

        process = server_manager.processes.get(server_name)
        if process is None:
            raise HTTPException(503, f"Server '{server_name}' failed to start")

        collector = MetricsCollector(server_name)
        sem = server_manager.get_concurrency_semaphore(server_name)
        if sem is not None:
            if sem._value <= 0:
                collector.record_rejected_request("concurrency_limit")
                return Response(
                    content='{"error":"too many concurrent requests"}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": "1"},
                )
            await sem.acquire()

        try:
            # ── Network transport ────────────────────────────────────────────────
            if isinstance(process, NetworkSubprocessHandle):
                payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
                if process.transport == "http":
                    response, _upstream_session_id = await _proxy_to_http_server(process.base_url, payload, timeout=30.0, session_id=process.session_id, client=process.http_client)
                else:
                    response = await _proxy_to_sse_server(process.base_url, payload, timeout=30.0, client=process.sse_client)
                return JSONResponse(content=response)
            # ── stdio transport continues below ──────────────────────────────────

            try:
                request_payload = {
                    "id": 1,
                    "jsonrpc": "2.0",
                    "method": "tools/list"
                }

                # Response is matched by JSON-RPC ID by the per-process stdio router, so
                # the fixed id=1 here never collides with concurrent callers.
                try:
                    response_data = await get_stdio_router(process, server_name).request(
                        request_payload, timeout=_MCP_READ_TIMEOUT
                    )
                except (BrokenPipeError, OSError, StdioProcessClosed) as e:
                    raise HTTPException(503, f"Server '{server_name}' process pipe broken: {str(e)}")
                except StdioRequestTimeout:
                    raise HTTPException(504, f"Server '{server_name}' did not respond within {_MCP_READ_TIMEOUT} seconds")

                return JSONResponse(content=response_data)

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error listing tools for '{server_name}': {e}")
                raise HTTPException(500, f"Error communicating with server: {str(e)}")
        finally:
            if sem is not None:
                sem.release()

    @router.post("/{server_name}/mcp/tools/call", tags=["mcp"])
    async def call_tool(
        server_name: str,
        request_body: Dict[str, Any] = Body(
            ...,
            example={
                "name": "read_file",
                "arguments": {"path": "/tmp/test.txt"}
            }
        ),
        token: str = Depends(get_token)
    ):
        """
        Call a specific tool on the MCP server.
        """
        await auto_start_stopped_server(server_name)

        process = server_manager.processes.get(server_name)
        if process is None:
            raise HTTPException(503, f"Server '{server_name}' failed to start")

        collector = MetricsCollector(server_name)
        sem = server_manager.get_concurrency_semaphore(server_name)
        if sem is not None:
            if sem._value <= 0:
                collector.record_rejected_request("concurrency_limit")
                return Response(
                    content='{"error":"too many concurrent requests"}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": "1"},
                )
            await sem.acquire()

        try:
            # ── Network transport ────────────────────────────────────────────────
            if isinstance(process, NetworkSubprocessHandle):
                if "name" not in request_body:
                    raise HTTPException(400, "Tool name is required")
                payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": request_body}
                if process.transport == "http":
                    response, _upstream_session_id = await _proxy_to_http_server(process.base_url, payload, timeout=60.0, session_id=process.session_id, client=process.http_client)
                else:
                    response = await _proxy_to_sse_server(process.base_url, payload, timeout=60.0, client=process.sse_client)
                return JSONResponse(content=response)
            # ── stdio transport continues below ──────────────────────────────────

            try:
                if "name" not in request_body:
                    raise HTTPException(400, "Tool name is required")

                request_payload = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": request_body
                }

                # Tool calls can be long-running, so _MCP_READ_TIMEOUT is the upper bound.
                # The response is matched by JSON-RPC ID; on timeout the waiter is removed
                # and a late response is dropped instead of reaching the next request.
                try:
                    response_data = await get_stdio_router(process, server_name).request(
                        request_payload, timeout=_MCP_READ_TIMEOUT
                    )
                except (BrokenPipeError, OSError, StdioProcessClosed) as e:
                    raise HTTPException(503, f"Server '{server_name}' process pipe broken: {str(e)}")
                except StdioRequestTimeout:
                    # Persist the failure for observability before raising.
                    await server_manager.db.save_log_entry({
                        "server_name": server_name,
                        "stream": "error",
                        "content": f"Tool '{request_body.get('name', 'unknown')}' execution timed out after {_MCP_READ_TIMEOUT} seconds"
                    })
                    raise HTTPException(504, "Tool execution timed out")

                # Update last_used_at for idle cleanup
                await server_manager.update_last_used(server_name)

                return JSONResponse(content=response_data)

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error calling tool on '{server_name}': {e}")
                raise HTTPException(500, f"Error communicating with server: {str(e)}")
        finally:
            if sem is not None:
                sem.release()

    return router
