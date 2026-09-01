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
from .tool_error_tracker import record_tool_outcome as _record_tool_outcome
from .network_handle import NetworkSubprocessHandle
from .sse_handle import SseSubprocessHandle

security = HTTPBearer(auto_error=False)


def _is_unfilled(v) -> bool:
    """Return True if the LLM left this parameter at its None default."""
    return v is None


def _tool_label(request: dict) -> str:
    """Name to attribute an outcome to.

    For tools/call this is the tool name, so a single failing endpoint is
    visible; for anything else the JSON-RPC method is a good enough bucket.
    """
    method = request.get("method") or "unknown"
    if method == "tools/call":
        params = request.get("params")
        if isinstance(params, dict) and params.get("name"):
            return str(params["name"])
    return str(method)


def _mcp_result_text(result: dict) -> str:
    """Readable text from an MCP tool result's content blocks."""
    content = result.get("content")
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        joined = " ".join(p for p in parts if p).strip()
        if joined:
            return joined[:500]
    return str(result)[:500]


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


def readline_with_timeout(process: subprocess.Popen, timeout: float = _MCP_READ_TIMEOUT) -> str:
    """Read one line from process stdout with a timeout.

    Uses select() on Unix so the calling thread is not blocked indefinitely if the
    subprocess hangs. On Windows (where select() doesn't support pipes), falls back
    to a dedicated reader thread with a join timeout. Returns "" on timeout or EOF.

    Why select() and not asyncio.wait_for(): wait_for cancels the coroutine but
    leaves the OS thread blocked on readline(). ThreadPoolExecutor can only reclaim
    a slot when the thread *returns*, so the slot stays consumed forever. select()
    puts the timeout inside the thread itself — if nothing arrives in time, the
    thread returns "" immediately and frees its slot.

    The default timeout is overridable process-wide via the MCP_READ_TIMEOUT
    environment variable (see _MCP_READ_TIMEOUT); callers may also pass an
    explicit per-call timeout (e.g. shorter timeouts during initialization).
    """
    if os.name == "nt":
        # Windows: select() doesn't work on pipes — use a thread with join timeout.
        # Note: on timeout the reader thread stays alive (daemon, cleaned up at exit).
        # Production runs on Linux where the select() path is used instead.
        result: list = []

        def _read() -> None:
            try:
                result.append(process.stdout.readline())
            except (OSError, ValueError):
                result.append("")

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout=timeout)
        if result:
            return result[0]
        logger.warning("readline timed out after {}s (process pid={})", timeout, process.pid)
        return ""

    # Unix: select() confirms data is available, then readline() reads it.
    # Theoretical risk: readline() could block on a partial line without \n.
    # In practice this is safe because MCP JSON-RPC messages are always
    # newline-terminated, and the subprocess is opened with bufsize=1
    # (line-buffered). Using os.read() directly would bypass TextIOWrapper's
    # internal buffer and risk data loss, so we stay with readline().
    import select
    try:
        ready, _, _ = select.select([process.stdout], [], [], timeout)
        if ready:
            return process.stdout.readline()
        logger.warning("readline timed out after {}s (process pid={})", timeout, process.pid)
        return ""
    except (OSError, ValueError):
        return ""


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
                stderr_output = get_stderr_tail(stderr_key, 50) or "No stderr available"
                logger.error(f"Process died during initialization (exit code: {process.returncode}). stderr: {stderr_output}")
                return False

            # Cap per-read timeout to remaining time so the overall deadline is respected
            remaining = max(timeout - (time.time() - start_time), 0.5)
            read_timeout = min(remaining, 30.0)
            response_line = readline_with_timeout(process, timeout=read_timeout).strip()
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

        # Use drained buffer for stderr context (never blocks)
        stderr_output = get_stderr_tail(stderr_key, 50)
        if stderr_output:
            logger.error(f"Process stderr: {stderr_output}")

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
          [mcp.bad_response]   ERROR — stdout line is not valid JSON.
                                       Root cause: tool wrote plain text/traceback to stdout.
                                       Check stderr drainer logs for the real error.
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
                        response = await _proxy_to_sse_server(process.base_url, request)
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
                        return JSONResponse(content=response)

                # ── stdio transport: write to stdin, read from stdout ────────────
                try:
                    msg = json.dumps(request)
                    async with _get_io_lock(server_name):
                        try:
                            process.stdin.write(msg + "\n")
                            process.stdin.flush()
                        except (BrokenPipeError, OSError) as e:
                            # CAUGHT: [mcp.process_died] — stdin write failed mid-request.
                            # Root cause: subprocess crashed between the process.poll() check above
                            # and this write. Attaches stderr tail for crash diagnosis.
                            elapsed_ms = int((time.monotonic() - t0) * 1000)
                            stderr_tail = get_stderr_tail(server_name, 20)
                            _log.error(
                                f"[mcp.process_died] {ctx} elapsed={elapsed_ms}ms — broken pipe: {e}"
                                + (f"\nstderr:\n{stderr_tail}" if stderr_tail else "")
                            )
                            raise HTTPException(503, f"Server '{server_name}' process pipe broken: {str(e)}")

                        # readline_with_timeout uses select() internally so this thread returns
                        # after _MCP_READ_TIMEOUT seconds instead of blocking forever (no stuck
                        # asyncio worker threads / ThreadPoolExecutor exhaustion on a hung server).
                        response_line = await asyncio.to_thread(readline_with_timeout, process, _MCP_READ_TIMEOUT)
                        elapsed_ms = int((time.monotonic() - t0) * 1000)

                        if not response_line:
                            # CAUGHT: [mcp.timeout] — subprocess alive but produced no output in time.
                            # Root cause: tool is blocking on a slow operation. Common causes:
                            #   • DB connection with no query timeout (hangs indefinitely on refusal)
                            #   • HTTP call to an API with no timeout set
                            #   • Tool waiting on a lock or resource held by another process
                            _log.warning(f"[mcp.timeout] {ctx} elapsed={elapsed_ms}ms — server did not respond within {_MCP_READ_TIMEOUT}s")
                            _record_tool_outcome(
                                server_name, _tool_label(request), "timeout",
                                f"no response within {_MCP_READ_TIMEOUT}s",
                            )
                            raise HTTPException(504, f"Server '{server_name}' did not respond within {_MCP_READ_TIMEOUT} seconds")

                    # LOGGED: [mcp.slow] — response arrived but took longer than threshold.
                    # Not an error but a leading indicator that the downstream is degraded.
                    # Configure via FMCP_SLOW_REQUEST_MS (default: 5000).
                    _slow_ms = int(os.getenv("FMCP_SLOW_REQUEST_MS", "5000"))
                    if elapsed_ms > _slow_ms:
                        _log.warning(f"[mcp.slow] {ctx} elapsed={elapsed_ms}ms — response was slow")

                    try:
                        response_data = json.loads(response_line)
                    except json.JSONDecodeError as e:
                        # CAUGHT: [mcp.bad_response] — stdout line is not valid JSON.
                        # Root cause: tool printed a plain-text error, Python traceback,
                        # or startup message to stdout instead of stderr.
                        # Next step: look at stderr drainer logs for the real error text.
                        _log.error(f"[mcp.bad_response] {ctx} elapsed={elapsed_ms}ms — invalid JSON: {e} raw={response_line[:300]}")
                        raise HTTPException(502, "MCP server returned invalid JSON")

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
                        _record_tool_outcome(
                            server_name, _tool_label(request), "error",
                            err.get("message") if isinstance(err, dict) else str(err),
                        )
                    else:
                        # A tool-level failure arrives as isError inside a
                        # successful result, not as a JSON-RPC error. This is
                        # where a broken SQL connection actually shows up.
                        _result = response_data.get("result")
                        if isinstance(_result, dict) and _result.get("isError"):
                            _text = _mcp_result_text(_result)
                            _log.warning(
                                f"[mcp.tool_error] {ctx} elapsed={elapsed_ms}ms — "
                                f"isError: {_sanitize_log_field(_text)}"
                            )
                            _record_tool_outcome(
                                server_name, _tool_label(request), "tool_error", _text
                            )
                        else:
                            _log.info(f"[mcp.ok] {ctx} elapsed={elapsed_ms}ms")
                            _record_tool_outcome(
                                server_name, _tool_label(request), "success"
                            )

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

                # ── SSE transport: forward to external HTTP server ───────────
                # SseSubprocessHandle wraps an MCP server that speaks HTTP/SSE natively
                # (e.g. servers started with supergateway). Forward via httpx instead of stdin.
                if isinstance(process, SseSubprocessHandle):
                    import httpx
                    messages_url = f"{process.sse_url.rstrip('/')}/messages/"
                    sse_stream_url = f"{process.sse_url.rstrip('/')}/sse"
                    try:
                        async with httpx.AsyncClient(
                            timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)
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
                        # CAUGHT: sse_proxy_error metric — httpx failed to reach the
                        # external SSE server. Could be a connect timeout (server not
                        # ready), HTTP 5xx, or network-level failure.
                        completion_status = "error"
                        collector.record_error("sse_proxy_error")
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    return  # done for SSE transport — don't fall through to stdin path
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
                    # readline_with_timeout uses select() internally so this thread returns
                    # after _MCP_READ_TIMEOUT seconds instead of blocking forever, keeping the
                    # ThreadPoolExecutor pool healthy for other servers even if this one hangs.
                    response_line = await asyncio.to_thread(readline_with_timeout, process, _MCP_READ_TIMEOUT)
                    if not response_line:
                        elapsed_ms = int((time.monotonic() - t0_sse) * 1000)
                        if process.poll() is not None:
                            # CAUGHT: [mcp.sse.process_exited] — subprocess exited mid-stream.
                            # readline returned "" because the pipe closed (EOF), not a timeout.
                            # process.returncode tells you how it died; stderr tail shows why.
                            stderr_tail = get_stderr_tail(server_name, 20)
                            logger.error(
                                f"[mcp.sse.process_exited] {sse_ctx} elapsed={elapsed_ms}ms chunks={chunk_count} returncode={process.returncode}"
                                + (f"\nstderr:\n{stderr_tail}" if stderr_tail else "")
                            )
                            break
                        # Process is alive but produced nothing within the timeout — send a
                        # keep-alive SSE comment to prevent the client from closing the connection
                        # rather than aborting the stream outright.
                        # LOGGED: [mcp.sse.keepalive] DEBUG — expected for slow-running tools.
                        logger.debug(f"[mcp.sse.keepalive] {sse_ctx} elapsed={elapsed_ms}ms")
                        yield ": keep-alive\n\n"
                        continue

                    chunk_count += 1
                    # LOGGED: [mcp.sse.chunk] DEBUG — one line from subprocess stdout.
                    logger.debug(f"[mcp.sse.chunk] {sse_ctx} chunk={chunk_count} data={response_line.strip()[:200]}")
                    yield f"data: {response_line.strip()}\n\n"

                    try:
                        response_data = json.loads(response_line)
                        if "error" in response_data:
                            # CAUGHT: [mcp.sse.error_response] — tool sent an error chunk.
                            # Stream is still forwarded to the client.
                            # Root cause: same as [mcp.error_response] on the /mcp endpoint.
                            err = response_data["error"]
                            err_code = err.get("code") if isinstance(err, dict) else None
                            err_msg = _sanitize_log_field(err.get("message") if isinstance(err, dict) else str(err))
                            elapsed_ms = int((time.monotonic() - t0_sse) * 1000)
                            logger.warning(f"[mcp.sse.error_response] {sse_ctx} elapsed={elapsed_ms}ms code={err_code} message={err_msg}")
                            completion_status = "error_response"
                        if "result" in response_data:
                            # LOGGED: [mcp.sse.ok] — tool completed normally.
                            # Reset completion_status to "success" even if a prior chunk
                            # contained an error — the stream ended cleanly with a result.
                            elapsed_ms = int((time.monotonic() - t0_sse) * 1000)
                            completion_status = "success"
                            logger.info(f"[mcp.sse.ok] {sse_ctx} elapsed={elapsed_ms}ms chunks={chunk_count}")
                            break
                    except json.JSONDecodeError:
                        # LOGGED: [mcp.sse.non_json] DEBUG — non-JSON line silently forwarded.
                        # Some tools stream plain-text progress messages before the final result.
                        logger.debug(f"[mcp.sse.non_json] {sse_ctx} chunk={chunk_count} raw={response_line.strip()[:200]}")

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
                    # readline_with_timeout runs inside the thread and uses select() to
                    # enforce the timeout at the OS level, ensuring the thread returns and
                    # its pool slot is freed if this server hangs.
                    response_line = await asyncio.to_thread(
                        readline_with_timeout, process, _MCP_READ_TIMEOUT
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
                    # readline_with_timeout uses select() inside the thread so the thread
                    # exits on timeout rather than blocking the ThreadPoolExecutor slot forever.
                    # Without this, a single hanging tool call occupies a thread indefinitely;
                    # enough concurrent hangs will exhaust the pool and block all other servers.
                    response_line = await asyncio.to_thread(
                        readline_with_timeout, process, _MCP_READ_TIMEOUT
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
