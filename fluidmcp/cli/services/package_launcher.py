import os
import json
import select as _select
import subprocess
import shutil
import asyncio
import time
import threading
import httpx
from typing import Union, Dict, Any, Iterator, AsyncIterator, Optional, Tuple
from pathlib import Path
from loguru import logger
from fastapi import Request, APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..utils.env_utils import is_placeholder
from .metrics import MetricsCollector, RequestTimer
from fastapi.responses import Response
from .network_handle import NetworkSubprocessHandle
from .sse_handle import SseSubprocessHandle

security = HTTPBearer(auto_error=False)


def _sanitize_log_field(value: str, max_len: int = 200) -> str:
    """Strip CR/LF/control characters from user-controlled values before logging."""
    sanitized = "".join(ch for ch in str(value) if ch.isprintable() and ch not in "\r\n")
    return sanitized[:max_len]

# Max seconds to wait for an MCP subprocess to write a response line.
# Overridable via the MCP_READ_TIMEOUT environment variable.
#
# Why select() and not asyncio.wait_for():
# wait_for cancels the coroutine but leaves the OS thread blocked on readline().
# ThreadPoolExecutor can only reclaim a slot when the thread *returns*, so the
# slot stays consumed forever. select() puts the timeout inside the thread itself —
# if nothing arrives in time, the thread returns "" immediately and frees its slot.
_MCP_READ_TIMEOUT = float(os.environ.get("MCP_READ_TIMEOUT", "45"))


def _readline_with_timeout(stdout, timeout: float) -> str:
    """Read one line from a subprocess stdout pipe, with a hard thread-level timeout.

    This function is designed to be called via asyncio.to_thread() so that the
    event loop is not blocked. The key guarantee it provides over a plain
    readline() call is that it will always return within `timeout` seconds,
    ensuring the ThreadPoolExecutor slot is freed even if the MCP subprocess
    hangs indefinitely.

    How it works:
        select.select() is called first with the given timeout. It blocks the
        OS thread until either data is available on stdout OR the timeout expires.
        - If data arrives in time:  select returns stdout in the ready-list and
          we call readline() which returns immediately (data is already buffered).
        - If the timeout expires:   select returns an empty ready-list, and we
          return "" without touching readline() at all.

    Callers check for the empty-string return value and raise HTTPException(504).

    Args:
        stdout: The stdout pipe of a subprocess.Popen instance.
        timeout: Maximum seconds to wait before giving up.

    Returns:
        The next line (including the trailing newline) if data arrived in time,
        or "" if the timeout elapsed without any data.
    """
    ready, _, _ = _select.select([stdout], [], [], timeout)
    if not ready:
        return ""
    return stdout.readline()


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

async def _proxy_to_sse_server(sse_url: str, payload: dict, timeout: float = 60.0) -> dict:
    """
    Forward a JSON-RPC request to an SSE MCP server via POST /messages/.

    Args:
        sse_url:  Base URL of the SSE server (e.g. "http://127.0.0.1:8000").
        payload:  JSON-RPC 2.0 dict to send.
        timeout:  HTTP request timeout in seconds.

    Returns:
        Parsed JSON response dict.

    Raises:
        HTTPException on any HTTP or connection error.
    """
    messages_url = f"{sse_url.rstrip('/')}/messages/"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(messages_url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            e.response.status_code,
            f"SSE server returned HTTP {e.response.status_code}"
        )
    except httpx.ConnectError:
        raise HTTPException(
            503,
            f"Cannot reach SSE server at {sse_url}. Is it still running?"
        )
    except Exception as e:
        logger.error(f"SSE proxy error → {messages_url}: {e}")
        raise HTTPException(500, f"SSE proxy error: {str(e)}")

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

    # Use the caller-supplied shared pool when available. If not (e.g. tool
    # discovery at startup, or SSE fallback paths), create a short-lived client
    # and close it in the finally block so connections don't leak.
    owned_client = client is None
    if owned_client:
        client = httpx.AsyncClient(timeout=timeout)

    try:
        resp = await client.post(mcp_url, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        upstream_session_id = resp.headers.get("mcp-session-id")

        if is_notification:
            return None, upstream_session_id

        # FastMCP returns text/event-stream even for non-streaming responses.
        # Unwrap the SSE envelope to get the plain JSON-RPC payload.
        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            for line in resp.text.splitlines():
                if line.startswith("data: "):
                    return json.loads(line[6:]), upstream_session_id
            raise Exception(f"No data line in SSE response: {resp.text!r}")
        return resp.json(), upstream_session_id
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

        # Initialize MCP server
        if not initialize_mcp_server(process):
            error_msg = f"Failed to initialize MCP server for {pkg}"
            if placeholders_found:
                error_msg += (
                    f"\n\nPossible cause: {len(placeholders_found)} placeholder environment variable(s) detected."
                    f"\nPlease configure: {', '.join([k for k, v in placeholders_found])}"
                    f"\n\nTo fix: fmcp edit-env {pkg}"
                )
            logger.warning(error_msg)

        logger.debug(f"Launched MCP server process for package: {pkg}")
        return pkg, None, process  # router is None — callers use create_dynamic_router(server_manager)

    except FileNotFoundError:
        logger.exception("Command not found")
        return None, None, None
    except Exception:
        logger.exception("Error launching MCP server")
        return None, None, None
    



def initialize_mcp_server(process: subprocess.Popen, timeout: int = 30) -> bool:
    """
    Initialize MCP server with proper handshake.

    Args:
        process: Subprocess.Popen instance
        timeout: Timeout in seconds (default: 30, increased for npx -y downloads)

    Returns:
        True if initialization successful
    """
    try:
        # Check if process is already dead
        if process.poll() is not None:
            stderr_output = process.stderr.read() if process.stderr else "No stderr available"
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

        logger.debug(f"Sending initialize request: {json.dumps(init_request)}")
        try:
            process.stdin.write(json.dumps(init_request) + "\n")
            process.stdin.flush()
            logger.debug("Initialize request sent successfully")
        except (BrokenPipeError, OSError) as e:
            logger.error(f"Failed to write initialize request (process likely died): {e}")
            return False

        # Wait for response
        start_time = time.time()
        lines_received = []
        non_json_lines = []

        while time.time() - start_time < timeout:
            if process.poll() is not None:
                stderr_output = process.stderr.read() if process.stderr else "No stderr available"
                logger.error(f"Process died during initialization (exit code: {process.returncode}). stderr: {stderr_output}")
                return False

            response_line = process.stdout.readline().strip()
            if response_line:
                lines_received.append(response_line)
                logger.debug(f"Received line: {response_line[:200]}")
                try:
                    response = json.loads(response_line)
                    # Check if this is the initialize response
                    if response.get("id") == 0 and "result" in response:
                        # Send initialized notification
                        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
                        logger.debug(f"Sending initialized notification: {json.dumps(notif)}")
                        try:
                            process.stdin.write(json.dumps(notif) + "\n")
                            process.stdin.flush()
                        except (BrokenPipeError, OSError) as e:
                            logger.error(f"Failed to send initialized notification: {e}")
                            return False

                        if non_json_lines:
                            logger.info(f"MCP server initialized successfully (skipped {len(non_json_lines)} non-JSON log lines)")
                        else:
                            logger.info("MCP server initialized successfully")
                        return True
                except json.JSONDecodeError:
                    # Not JSON - likely a log message from the server
                    # Some servers output logs to stdout instead of stderr
                    non_json_lines.append(response_line[:200])
                    if len(non_json_lines) <= 5:
                        logger.debug(f"Skipping non-JSON line: {response_line[:200]}")
                    continue

            time.sleep(0.1)

        logger.error(f"MCP initialization timeout after {timeout} seconds")
        if lines_received:
            logger.error(f"Received {len(lines_received)} lines. First few: {lines_received[:3]}")
        else:
            logger.error("No output received from MCP server during initialization")

        # Try to read stderr for context
        try:
            stderr_output = process.stderr.read() if process.stderr else None
            if stderr_output:
                logger.error(f"Process stderr: {stderr_output[:500]}")
        except Exception:
            # Intentional: stderr read can fail if process terminated - safe to ignore
            pass

        return False
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
    _io_locks: Dict[str, asyncio.Lock] = {}

    def _get_io_lock(name: str) -> asyncio.Lock:
        if name not in _io_locks:
            _io_locks[name] = asyncio.Lock()
        return _io_locks[name]

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
        Proxy JSON-RPC requests to running MCP servers.

        Args:
            server_name: Name of the target server
            request: JSON-RPC request payload
        """
        # Initialize metrics collector
        collector = MetricsCollector(server_name)
        method = _sanitize_log_field(request.get("method", "unknown"))
        params = request.get("params", {})
        tool_name = _sanitize_log_field(params.get("name", "")) if method == "tools/call" else None
        tool_args_keys = [_sanitize_log_field(k) for k in sorted(params.get("arguments", {}).keys())] if method == "tools/call" else []
        request_id = _sanitize_log_field(str(request.get("id", "-")))

        ctx = f"server={server_name} method={method} req_id={request_id}"
        if tool_name:
            ctx += f" tool={tool_name} args={tool_args_keys}"

        t0 = time.monotonic()

        # Track request with metrics (RequestTimer automatically records all errors)
        # HTTPExceptions raised within this context are tracked as error_type="network_error"
        # via RequestTimer.__exit__ → _categorize_error() → name-based matching
        with RequestTimer(collector, method):
            await auto_start_stopped_server(server_name)

            process = server_manager.processes.get(server_name)
            if process is None:
                raise HTTPException(503, f"Server '{server_name}' failed to start")

            # Check if process is alive (stdio only — SSE/Network handles don't have .poll())
            if not isinstance(process, (SseSubprocessHandle, NetworkSubprocessHandle)) and process.poll() is not None:
                raise HTTPException(503, f"Server '{server_name}' is not running (process died)")

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
                        response = await _proxy_to_sse_server(process.base_url, request)
                    response_headers = {"Mcp-Session-Id": upstream_session_id} if upstream_session_id else None
                    if response is None:
                        # JSON-RPC notification (e.g. notifications/initialized) — the
                        # spec defines no response body for these; ack with empty 202.
                        return Response(status_code=202, headers=response_headers)
                    return JSONResponse(content=response, headers=response_headers)

                # ── SSE transport: forward via HTTP ─────────────────────────────
                if isinstance(process, SseSubprocessHandle):
                    with RequestTimer(collector, request.get("method", "unknown")):
                        response = await _proxy_to_sse_server(process.sse_url, request)
                        return JSONResponse(content=response)

                # ── stdio transport ──────────────────────────────────────────────
                try:
                    # Send request to MCP server
                    msg = json.dumps(request)
                    async with _get_io_lock(server_name):
                        try:
                            process.stdin.write(msg + "\n")
                            process.stdin.flush()
                        except (BrokenPipeError, OSError) as e:
                            raise HTTPException(503, f"Server '{server_name}' process pipe broken: {str(e)}")

                        # Wait for the MCP subprocess to write its JSON-RPC response.
                        # _readline_with_timeout runs in a thread (via to_thread) and uses
                        # select() internally, so the thread itself exits after _MCP_READ_TIMEOUT
                        # seconds if the server hangs — freeing the ThreadPoolExecutor slot.
                        # A plain readline() here would block the thread forever on a hung server,
                        # eventually exhausting the pool and making all healthy servers unreachable.
                        response_line = await asyncio.to_thread(
                            _readline_with_timeout, process.stdout, _MCP_READ_TIMEOUT
                        )
                        if not response_line:
                            # Empty string means select() timed out — server did not respond.
                            raise HTTPException(504, f"Server '{server_name}' did not respond within {_MCP_READ_TIMEOUT} seconds")
                    response_data = json.loads(response_line)

                    # Update last_used_at for idle cleanup
                    await server_manager.update_last_used(server_name)

                    return JSONResponse(content=response_data)

                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Error proxying request to '{server_name}': {e}")
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

        async def event_generator() -> AsyncIterator[str]:
            completion_status = "success"
            try:
                # Track streaming session when generator starts executing
                collector.increment_active_streams()

                # ── Network transport: forward to external HTTP server ───────
                if isinstance(process, NetworkSubprocessHandle):
                    if process.transport == "http":
                        try:
                            response, _upstream_session_id = await _proxy_to_http_server(process.base_url, request, session_id=process.session_id, client=process.http_client)
                            if response is not None:
                                # JSON-RPC notifications have no response to relay.
                                yield f"data: {json.dumps(response)}\n\n"
                        except Exception as e:
                            completion_status = "error"
                            collector.record_error("http_proxy_error")
                            yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    else:
                        import httpx
                        messages_url = f"{process.base_url.rstrip('/')}/messages/"
                        sse_stream_url = f"{process.base_url.rstrip('/')}/sse"
                        try:
                            async with httpx.AsyncClient(
                                timeout=httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)
                            ) as client:
                                await client.post(messages_url, json=request)
                                async with client.stream("GET", sse_stream_url) as resp:
                                    async for line in resp.aiter_lines():
                                        if line.startswith("data: "):
                                            data = line[6:]
                                            yield f"data: {data}\n\n"
                                            try:
                                                parsed = json.loads(data)
                                                if "result" in parsed:
                                                    break
                                            except json.JSONDecodeError:
                                                pass
                        except Exception as e:
                            completion_status = "error"
                            collector.record_error("sse_proxy_error")
                            yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    return  # done for network transport — don't fall through to stdin path
                # ── stdio transport continues below ──────────────────────────

                sse_method = _sanitize_log_field(request.get("method", "unknown"))
                sse_params = request.get("params", {})
                sse_tool_name = _sanitize_log_field(sse_params.get("name", "")) if sse_method == "tools/call" else None
                sse_tool_args_keys = [_sanitize_log_field(k) for k in sorted(sse_params.get("arguments", {}).keys())] if sse_method == "tools/call" else []
                sse_ctx = f"server={server_name} method={sse_method} req_id={_sanitize_log_field(str(request.get('id', '-')))}"
                if sse_tool_name:
                    sse_ctx += f" tool={sse_tool_name} args={sse_tool_args_keys}"
                t0_sse = time.monotonic()
                chunk_count = 0

                msg = json.dumps(request)
                async with _get_io_lock(server_name):
                    try:
                        process.stdin.write(msg + "\n")
                        process.stdin.flush()
                    except (BrokenPipeError, OSError) as e:
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

                while True:
                    # Read the next line from the MCP subprocess for streaming.
                    # Uses _readline_with_timeout (via to_thread) so the thread returns
                    # after _MCP_READ_TIMEOUT seconds if no data arrives, keeping the
                    # ThreadPoolExecutor pool healthy for other servers.
                    # An empty string indicates a timeout (select() expired);
                    # a None/falsy non-empty value indicates EOF (process closed stdout).
                    response_line = await asyncio.to_thread(
                        _readline_with_timeout, process.stdout, _MCP_READ_TIMEOUT
                    )
                    if not response_line:
                        elapsed_ms = int((time.monotonic() - t0_sse) * 1000)
                        if response_line == "":
                            # Timeout: server never wrote data within the deadline.
                            logger.warning(f"[mcp.sse.timeout] {sse_ctx} elapsed={elapsed_ms}ms chunks={chunk_count} — server did not respond within {_MCP_READ_TIMEOUT}s")
                            yield f"data: {json.dumps({'error': f'Server did not respond within {_MCP_READ_TIMEOUT} seconds'})}\n\n"
                        # Either timeout or EOF — stop streaming either way.
                        break

                    chunk_count += 1
                    logger.debug(f"[mcp.sse.chunk] {sse_ctx} chunk={chunk_count} data={response_line.strip()[:200]}")
                    yield f"data: {response_line.strip()}\n\n"

                    try:
                        response_data = json.loads(response_line)
                        if "error" in response_data:
                            err = response_data["error"]
                            err_code = err.get("code") if isinstance(err, dict) else None
                            err_msg = _sanitize_log_field(err.get("message") if isinstance(err, dict) else str(err))
                            elapsed_ms = int((time.monotonic() - t0_sse) * 1000)
                            logger.warning(f"[mcp.sse.error_response] {sse_ctx} elapsed={elapsed_ms}ms code={err_code} message={err_msg}")
                            completion_status = "error_response"
                        if "result" in response_data:
                            # Reset to success even if a prior chunk contained an error —
                            # the stream ended cleanly with a result.
                            elapsed_ms = int((time.monotonic() - t0_sse) * 1000)
                            completion_status = "success"
                            logger.info(f"[mcp.sse.ok] {sse_ctx} elapsed={elapsed_ms}ms chunks={chunk_count}")
                            break
                    except json.JSONDecodeError:
                        logger.debug(f"[mcp.sse.non_json] {sse_ctx} chunk={chunk_count} raw={response_line.strip()[:200]}")

            except Exception as e:
                elapsed_ms = int((time.monotonic() - t0_sse) * 1000)
                completion_status = "error"
                logger.error(f"[mcp.sse.error] {sse_ctx} elapsed={elapsed_ms}ms — {type(e).__name__}: {e}", exc_info=True)
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                # Record streaming metrics
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
                    response = await _proxy_to_sse_server(process.base_url, payload, timeout=30.0)
                return JSONResponse(content=response)
            # ── stdio transport continues below ──────────────────────────────────

            try:
                request_payload = {
                    "id": 1,
                    "jsonrpc": "2.0",
                    "method": "tools/list"
                }

                msg = json.dumps(request_payload)
                async with _get_io_lock(server_name):
                    try:
                        process.stdin.write(msg + "\n")
                        process.stdin.flush()
                    except (BrokenPipeError, OSError) as e:
                        raise HTTPException(503, f"Server '{server_name}' process pipe broken: {str(e)}")

                    # Wait for the tools/list response from the MCP subprocess.
                    # _readline_with_timeout runs inside the thread and uses select() to
                    # enforce the timeout at the OS level, ensuring the thread returns and
                    # its pool slot is freed if this server hangs.
                    response_line = await asyncio.to_thread(
                        _readline_with_timeout, process.stdout, _MCP_READ_TIMEOUT
                    )
                    if not response_line:
                        # select() timed out — no response received within the deadline.
                        raise HTTPException(504, f"Server '{server_name}' did not respond within {_MCP_READ_TIMEOUT} seconds")
                response_data = json.loads(response_line)

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
                    response = await _proxy_to_sse_server(process.base_url, payload, timeout=60.0)
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

                msg = json.dumps(request_payload)
                async with _get_io_lock(server_name):
                    try:
                        process.stdin.write(msg + "\n")
                        process.stdin.flush()
                    except (BrokenPipeError, OSError) as e:
                        raise HTTPException(503, f"Server '{server_name}' process pipe broken: {str(e)}")

                    # Wait for the tool execution response from the MCP subprocess.
                    # Tool calls can be long-running, so _MCP_READ_TIMEOUT is the upper bound.
                    # _readline_with_timeout uses select() inside the thread so the thread
                    # exits on timeout rather than blocking the ThreadPoolExecutor slot forever.
                    # Without this, a single hanging tool call occupies a thread indefinitely;
                    # enough concurrent hangs will exhaust the pool and block all other servers.
                    response_line = await asyncio.to_thread(
                        _readline_with_timeout, process.stdout, _MCP_READ_TIMEOUT
                    )
                    if not response_line:
                        # select() timed out — persist the failure for observability before raising.
                        await server_manager.db.save_log_entry({
                            "server_name": server_name,
                            "stream": "error",
                            "content": f"Tool '{request_body.get('name', 'unknown')}' execution timed out after {_MCP_READ_TIMEOUT} seconds"
                        })
                        raise HTTPException(504, "Tool execution timed out")

                response_data = json.loads(response_line)

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
