import os
import json
import select as _select
import subprocess
import shutil
import asyncio
import time
import threading
from collections import deque
import uuid
from typing import Union, Dict, Any, Iterator, AsyncIterator
from pathlib import Path
from loguru import logger
from fastapi import FastAPI, Request, APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn

from ..utils.env_utils import is_placeholder
from .metrics import MetricsCollector, RequestTimer
from .sse_handle import SseSubprocessHandle

security = HTTPBearer(auto_error=False)

# Max seconds to wait for an MCP subprocess to write a response line.
# Overridable via the MCP_READ_TIMEOUT environment variable.
#
# Why select() and not asyncio.wait_for():
# wait_for cancels the coroutine but leaves the OS thread blocked on readline().
# ThreadPoolExecutor can only reclaim a slot when the thread *returns*, so the
# slot stays consumed forever. select() puts the timeout inside the thread itself —
# if nothing arrives in time, the thread returns "" immediately and frees its slot.
_MCP_READ_TIMEOUT = float(os.environ.get("MCP_READ_TIMEOUT", "45"))

# key → (lock, deque) for stderr drainer buffers
_stderr_buffers: Dict[str, tuple] = {}


def start_stderr_drainer(process: subprocess.Popen, key: str) -> None:
    """Start a daemon thread that continuously drains stderr for a subprocess.

    Without this, any MCP server that writes enough to stderr will fill the
    64 KB OS pipe buffer and freeze — stopping stdout communication too.
    The buffer stores the last 200 lines for crash diagnosis.
    """
    lock = threading.Lock()
    buf: deque = deque(maxlen=200)
    _stderr_buffers[key] = (lock, buf)

    def _drain() -> None:
        try:
            for line in process.stderr:
                stripped = line.rstrip()
                with lock:
                    buf.append(stripped)
                logger.debug("[{}] stderr: {}", key, stripped)
        except (OSError, ValueError):
            pass
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


def readline_with_timeout(process: subprocess.Popen, timeout: float = 30.0) -> str:
    """Read one line from process stdout with a timeout.

    Uses select() on Unix. On Windows falls back to a reader thread + join.
    Returns "" on timeout or EOF.
    """
    if os.name == "nt":
        result: list = []

        def _read() -> None:
            try:
                result.append(process.stdout.readline())
            except (OSError, ValueError):
                result.append("")

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout=timeout)
        return result[0] if result else ""

    try:
        ready, _, _ = _select.select([process.stdout], [], [], timeout)
        if ready:
            return process.stdout.readline()
        return ""
    except (OSError, ValueError):
        return ""


def _readline_with_timeout(stdout, timeout: float) -> str:
    """Read one line from stdout with a hard thread-level timeout via select().

    Returns the line if data arrived in time, or "" if the timeout elapsed.
    Callers treat "" as a hung server and raise HTTPException(504).
    """
    ready, _, _ = _select.select([stdout], [], [], timeout)
    if not ready:
        return ""
    return stdout.readline()


# ── Per-server stdio dispatcher ────────────────────────────────────────────────
# MCP over stdio is fundamentally single-tenant: one process, one pipe, one
# request at a time. A simple asyncio.Lock serialises writes but callers still
# read from shared stdout, so response N+1 can be stolen by the waiter for N.
#
# Solution: one asyncio.Queue per server. Each caller drops a (request_json,
# Future) tuple into the queue and awaits its Future. A single background
# worker drains the queue: write → readline → set_result. That guarantees every
# caller gets exactly its own response. Requests that arrive when the queue is
# full receive an immediate 429.
#
# Queue depth = 200 gives ≈4s of buffering at 50 req/s before we start
# rejecting, which is a reasonable backpressure point.
_QUEUE_DEPTH = int(os.getenv("FMCP_STDIO_QUEUE_DEPTH", "200"))

# server_name → asyncio.Queue[tuple[str, asyncio.Future]]
_stdio_queues: Dict[str, asyncio.Queue] = {}
# server_name → asyncio.Task (the background worker)
_stdio_workers: Dict[str, asyncio.Task] = {}


def _get_stdio_queue(server_name: str) -> asyncio.Queue:
    """Return (creating if needed) the request queue for this server."""
    q = _stdio_queues.get(server_name)
    if q is None:
        q = asyncio.Queue(maxsize=_QUEUE_DEPTH)
        _stdio_queues[server_name] = q
    return q


def _reset_stdio_queue(server_name: str) -> None:
    """Drain and discard the queue + worker for a server that is restarting.

    Stale (msg, fut) items from the dead process must not reach the new process;
    their futures are cancelled so callers receive a 503 instead of a wrong response.
    """
    task = _stdio_workers.pop(server_name, None)
    if task and not task.done():
        task.cancel()

    old_q = _stdio_queues.pop(server_name, None)
    if old_q is not None:
        while not old_q.empty():
            try:
                item = old_q.get_nowait()
                if item is not None:
                    _, fut = item
                    if not fut.done():
                        fut.cancel()
            except asyncio.QueueEmpty:
                break


async def _stdio_worker(server_name: str, process) -> None:
    """
    Background coroutine that serialises all stdio traffic for one server.
    Runs until it receives a sentinel (None) or the process dies.
    """
    q = _get_stdio_queue(server_name)
    while True:
        item = await q.get()
        if item is None:          # shutdown sentinel
            q.task_done()
            break
        msg, fut = item
        try:
            if process.poll() is not None:
                fut.set_exception(RuntimeError("process exited"))
                q.task_done()
                continue
            process.stdin.write(msg + "\n")
            process.stdin.flush()
            response_line = await asyncio.to_thread(
                _readline_with_timeout, process.stdout, _MCP_READ_TIMEOUT
            )
            if not response_line:
                fut.set_exception(RuntimeError(
                    f"server did not respond within {_MCP_READ_TIMEOUT}s"
                ))
            elif not fut.done():
                fut.set_result(response_line)
        except Exception as exc:
            if not fut.done():
                fut.set_exception(exc)
        finally:
            q.task_done()


def _ensure_stdio_worker(server_name: str, process) -> None:
    """Start the background worker for a server if not already running."""
    task = _stdio_workers.get(server_name)
    if task is None or task.done():
        task = asyncio.create_task(_stdio_worker(server_name, process))
        task.add_done_callback(
            lambda t: logger.error(
                f"[{server_name}] stdio worker crashed: {t.exception()}"
            ) if not t.cancelled() and t.exception() else None
        )
        _stdio_workers[server_name] = task


async def _dispatch_stdio(server_name: str, process, msg: str) -> str:
    """
    Submit msg to the server's worker queue and wait for the response line.
    Raises HTTPException(429) if the queue is full, HTTPException(503) on
    pipe/process errors.
    """
    _ensure_stdio_worker(server_name, process)
    q = _get_stdio_queue(server_name)
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    try:
        q.put_nowait((msg, fut))
    except asyncio.QueueFull:
        raise HTTPException(
            429,
            f"Server '{server_name}' is busy (queue full). Retry after a moment."
        )
    try:
        # Guard against the worker crashing after dequeuing but before resolving
        # the future — without a timeout the caller would hang indefinitely.
        return await asyncio.wait_for(fut, timeout=_MCP_READ_TIMEOUT + 5)
    except asyncio.TimeoutError:
        raise HTTPException(504, f"Server '{server_name}' worker timed out")
    except RuntimeError as exc:
        msg = str(exc)
        code = 504 if "did not respond" in msg else 503
        raise HTTPException(code, f"Server '{server_name}': {msg}")
    except (BrokenPipeError, OSError) as exc:
        raise HTTPException(503, f"Server '{server_name}' pipe broken: {exc}")


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
    import httpx

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

        router = create_mcp_router(pkg, process, process_lock)
        logger.debug(f"Created router for package: {pkg}")
        return pkg, router, process  # Return process for explicit registry

    except FileNotFoundError:
        logger.exception("Command not found")
        return None, None, None
    except Exception:
        logger.exception("Error launching MCP server")
        return None, None, None
    


def create_fastapi_jsonrpc_proxy(package_name: str, process: subprocess.Popen) -> FastAPI:
    app = FastAPI()
    process_lock = threading.Lock()
    @app.post(f"/{package_name}/mcp")
    async def proxy_jsonrpc(request: Request):
        try:
            jsonrpc_request = await request.body()
            jsonrpc_str = jsonrpc_request.decode() if isinstance(jsonrpc_request, bytes) else jsonrpc_request
            # Offload blocking stdin/stdout I/O to a worker thread
            def _communicate(payload: str) -> str:
                with process_lock:
                    process.stdin.write(payload + "\n")
                    process.stdin.flush()
                    return _readline_with_timeout(process.stdout, timeout=30.0)

            try:
                response_line = await asyncio.to_thread(_communicate, jsonrpc_str)
            except (BrokenPipeError, OSError) as e:
                return JSONResponse(status_code=503, content={"error": f"Process pipe broken: {e}"})
            if not response_line:
                return JSONResponse(status_code=504, content={"error": "MCP server did not respond within timeout"})
            return JSONResponse(content=json.loads(response_line))
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
    return app


def start_fastapi_in_thread(app: FastAPI, port: int):
    def run():
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    thread = threading.Thread(target=run, daemon=True)
    thread.start()


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
            response_line = _readline_with_timeout(process.stdout, timeout=read_timeout).strip()
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
    

def create_mcp_router(package_name: str, process: subprocess.Popen, process_lock: threading.Lock = None) -> APIRouter:
    

    # Create a lock if not provided
    if process_lock is None:
        process_lock = threading.Lock()

    router = APIRouter()

    @router.post(f"/{package_name}/mcp", tags=[package_name])
    async def proxy_jsonrpc(
        http_request: Request,
        request: Dict[str, Any] = Body(
            ...,
            example={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "",
                "params": {}
            }
        ), token: str = Depends(get_token)
    ):
        # Initialize metrics collector
        collector = MetricsCollector(package_name)
        method = request.get("method", "unknown")

        # Track request with metrics
        with RequestTimer(collector, method):
            try:
                # Extract all headers from incoming HTTP request
                all_headers = dict(http_request.headers)

                logger.info(f"[{package_name}] Received request: method={request.get('method')}, has_headers={bool(all_headers)}")

                # Only inject headers if this is a tools/call request
                if request.get("method") == "tools/call" and all_headers:
                    params = request.get("params", {})
                    if "arguments" not in params:
                        params["arguments"] = {}

                    logger.info(f"[{package_name}] HTTP headers: {list(all_headers.keys())}")
                    logger.info(f"[{package_name}] Arguments before injection: {list(params.get('arguments', {}).keys())}")

                    params["arguments"]["headers"] = all_headers
                    request["params"] = params

                    logger.info(f"[{package_name}] Arguments after injection: {list(params.get('arguments', {}).keys())}")

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
                                "serverInfo": {"name": package_name, "version": "1.0.0"}
                            }
                        },
                        headers={"mcp-session-id": str(uuid.uuid4())}
                    )
                if method == "notifications/initialized":
                    return Response(status_code=204)

                # Offload blocking stdin/stdout I/O to a worker thread
                msg = json.dumps(request)
                logger.debug(f"[{package_name}] Sending to MCP stdin: {msg[:200]}...")

                def _communicate_mcp(payload: str) -> str:
                    with process_lock:
                        process.stdin.write(payload + "\n")
                        process.stdin.flush()
                        return _readline_with_timeout(process.stdout, timeout=30.0)

                response_line = await asyncio.to_thread(_communicate_mcp, msg)
                logger.debug(f"[{package_name}] Received from stdout: {response_line[:200]}...")

                if not response_line:
                    return JSONResponse(status_code=504, content={"error": f"[{package_name}] MCP server did not respond within timeout"})
                return JSONResponse(content=json.loads(response_line))
            except Exception as e:
                logger.error(f"[{package_name}] Error in proxy: {e}", exc_info=True)
                return JSONResponse(status_code=500, content={"error": str(e)})
    
    # New SSE endpoint
    @router.post(f"/{package_name}/sse", tags=[package_name])
    async def sse_stream(
        http_request: Request,
        request: Dict[str, Any] = Body(
            ...,
            example={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "",
                "params": {}
            }
        ), token: str = Depends(get_token)
    ):
        # Extract all headers from incoming HTTP request
        all_headers = dict(http_request.headers)

        # Only inject headers if this is a tools/call request
        if request.get("method") == "tools/call" and all_headers:
            params = request.get("params", {})
            if "arguments" not in params:
                params["arguments"] = {}
            params["arguments"]["headers"] = all_headers
            request["params"] = params

        # Initialize metrics collector
        collector = MetricsCollector(package_name)

        async def event_generator() -> AsyncIterator[str]:
            completion_status = "success"
            try:
                # Track streaming session when generator starts
                collector.increment_active_streams()

                # Send request to MCP server (offloaded to worker thread)
                msg = json.dumps(request)

                def _send_request(payload: str) -> None:
                    with process_lock:
                        process.stdin.write(payload + "\n")
                        process.stdin.flush()

                await asyncio.to_thread(_send_request, msg)

                # Read from stdout and stream as SSE events
                while True:
                    response_line = await asyncio.to_thread(_readline_with_timeout, process.stdout, 30.0)
                    if not response_line:
                        break

                    logger.debug(f"Received from MCP: {response_line.strip()}")
                    yield f"data: {response_line.strip()}\n\n"

                    try:
                        response_data = json.loads(response_line)
                        if "result" in response_data:
                            break
                    except json.JSONDecodeError:
                        pass

            except (BrokenPipeError, OSError) as e:
                completion_status = "broken_pipe"
                collector.record_error("io_error")
                yield f"data: {json.dumps({'error': f'Process pipe broken: {str(e)}'})}\n\n"
            except Exception as e:
                completion_status = "error"
                # Send error as SSE event
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                # Record streaming metrics
                collector.record_streaming_request(completion_status)
                collector.decrement_active_streams()

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )
        
    @router.get(f"/{package_name}/mcp/tools/list", tags=[package_name])
    async def list_tools(token: str = Depends(get_token)):
        # Initialize metrics collector
        collector = MetricsCollector(package_name)

        # Track request with metrics
        with RequestTimer(collector, "tools/list"):
            try:
                # Pre-filled JSON-RPC request for tools/list
                request_payload = {
                    "id": 1,
                    "jsonrpc": "2.0",
                    "method": "tools/list"
                }

                # Offload blocking stdin/stdout I/O to a worker thread
                msg = json.dumps(request_payload)

                def _communicate_list() -> str:
                    with process_lock:
                        process.stdin.write(msg + "\n")
                        process.stdin.flush()
                        return _readline_with_timeout(process.stdout, timeout=30.0)

                response_line = await asyncio.to_thread(_communicate_list)

                if not response_line:
                    return JSONResponse(status_code=504, content={"error": "MCP server did not respond within timeout"})
                response_data = json.loads(response_line)
                return JSONResponse(content=response_data)

            except Exception as e:
                return JSONResponse(status_code=500, content={"error": str(e)})


    @router.post(f"/{package_name}/mcp/tools/call", tags=[package_name])
    async def call_tool(
        http_request: Request,
        request_body: Dict[str, Any] = Body(
            ...,
            alias="params",
            example={
                "name": "",
            }
        ), token: str = Depends(get_token)
    ):
        params = request_body

        # Initialize metrics collector
        collector = MetricsCollector(package_name)
        tool_name = params.get("name", "unknown")

        # Track request with metrics
        with RequestTimer(collector, f"tools/call:{tool_name}"):
            try:
                # Validate required fields
                if "name" not in params:
                    return JSONResponse(
                        status_code=400,
                        content={"error": "Tool name is required"}
                    )

                # Extract all headers from incoming HTTP request
                all_headers = dict(http_request.headers)

                # Only inject if headers actually exist
                if all_headers:
                    if "arguments" not in params:
                        params["arguments"] = {}
                    params["arguments"]["headers"] = all_headers

                # Construct complete JSON-RPC request
                request_payload = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": params
                }

                # Offload blocking stdin/stdout I/O to a worker thread
                msg = json.dumps(request_payload)

                def _communicate_call() -> str:
                    with process_lock:
                        process.stdin.write(msg + "\n")
                        process.stdin.flush()
                        return _readline_with_timeout(process.stdout, timeout=30.0)

                response_line = await asyncio.to_thread(_communicate_call)

                if not response_line:
                    return JSONResponse(status_code=504, content={"error": "MCP server did not respond within timeout"})
                response_data = json.loads(response_line)
                return JSONResponse(content=response_data)

            except json.JSONDecodeError:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Invalid JSON in request body"}
                )
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={"error": str(e)}
                )
    return router

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
        method = request.get("method", "unknown")

        # Track request with metrics (RequestTimer automatically records all errors)
        # HTTPExceptions raised within this context are tracked as error_type="network_error"
        # via RequestTimer.__exit__ → _categorize_error() → name-based matching
        with RequestTimer(collector, method):
            # Check if server exists
            if server_name not in server_manager.processes:
                raise HTTPException(404, f"Server '{server_name}' not found or not running")

            process = server_manager.processes[server_name]

            # Check if process is alive
            if process.poll() is not None:
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

            # ── SSE transport: forward via HTTP ─────────────────────────────
            if isinstance(process, SseSubprocessHandle):
                with RequestTimer(collector, request.get("method", "unknown")):
                    response = await _proxy_to_sse_server(process.sse_url, request)
                    return JSONResponse(content=response)
            # ── stdio transport continues below ─────────────────────────────

            try:
                # Dispatch through the per-server queue worker.
                # The worker is the only coroutine that writes to stdin and reads
                # from stdout, so each caller gets exactly its own response line.
                msg = json.dumps(request)
                response_line = await _dispatch_stdio(server_name, process, msg)

                if not response_line:
                    raise HTTPException(504, f"Server '{server_name}' timed out responding")
                response_data = json.loads(response_line)

                # Update last_used_at for idle cleanup
                await server_manager.update_last_used(server_name)

                return JSONResponse(content=response_data)

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error proxying request to '{server_name}': {e}")
                raise HTTPException(500, f"Error communicating with server: {str(e)}")

    @router.post("/{server_name}/sse", tags=["mcp"])
    async def sse_stream(
        server_name: str,
        request: Dict[str, Any] = Body(...),
        token: str = Depends(get_token)
    ):
        """
        Server-Sent Events streaming endpoint for long-running MCP operations.
        """
        # Update last_used_at for idle cleanup when SSE connection is opened
        await server_manager.update_last_used(server_name)

        # Initialize metrics collector
        collector = MetricsCollector(server_name)

        # Pre-validation (errors NOT tracked - occurs before streaming begins)
        #
        # Design Decision: These HTTPExceptions (404/503) are intentionally NOT wrapped
        # in RequestTimer because they represent pre-flight validation failures that occur
        # before any MCP protocol interaction begins. They are pure HTTP-layer errors.
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
        if server_name not in server_manager.processes:
            raise HTTPException(404, f"Server '{server_name}' not found or not running")

        process = server_manager.processes[server_name]

        if process.poll() is not None:
            raise HTTPException(503, f"Server '{server_name}' is not running")

        async def event_generator() -> AsyncIterator[str]:
            completion_status = "success"
            try:
                # Track streaming session when generator starts executing
                collector.increment_active_streams()

                # ── SSE transport: forward to external HTTP server ───────────
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
                        completion_status = "error"
                        collector.record_error("sse_proxy_error")
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    return  # done for SSE — don't fall through to stdin path
                # ── stdio transport continues below ──────────────────────────

                # Dispatch through the shared per-server queue worker so this
                # SSE request doesn't race with concurrent proxy_jsonrpc calls
                # for the same server's stdin/stdout pipe.
                msg = json.dumps(request)
                try:
                    response_line = await _dispatch_stdio(server_name, process, msg)
                except HTTPException as e:
                    if e.status_code == 429:
                        completion_status = "queue_full"
                        collector.record_error("queue_full")
                    else:
                        completion_status = "broken_pipe"
                        collector.record_error("io_error")
                    yield f"data: {json.dumps({'error': e.detail})}\n\n"
                    return

                if not response_line:
                    return
                yield f"data: {response_line.strip()}\n\n"
                # stdio MCP gives exactly one JSON-RPC response per request;
                # reading further from process.stdout here would steal responses
                # queued for concurrent callers.

            except Exception as e:
                completion_status = "error"
                logger.exception(f"Error in event generator for '{server_name}': {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                # Record streaming metrics
                collector.record_streaming_request(completion_status)
                collector.decrement_active_streams()

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
        if server_name not in server_manager.processes:
            raise HTTPException(404, f"Server '{server_name}' not found or not running")

        process = server_manager.processes[server_name]

        if process.poll() is not None:
            raise HTTPException(503, f"Server '{server_name}' is not running")

        # ── SSE transport ────────────────────────────────────────────────────
        if isinstance(process, SseSubprocessHandle):
            response = await _proxy_to_sse_server(
                process.sse_url,
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                timeout=30.0
            )
            return JSONResponse(content=response)
        # ── stdio transport continues below ──────────────────────────────────

        try:
            request_payload = {
                "id": 1,
                "jsonrpc": "2.0",
                "method": "tools/list"
            }
            msg = json.dumps(request_payload)
            response_line = await _dispatch_stdio(server_name, process, msg)
            response_data = json.loads(response_line)
            return JSONResponse(content=response_data)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error listing tools for '{server_name}': {e}")
            raise HTTPException(500, f"Error communicating with server: {str(e)}")

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
        if server_name not in server_manager.processes:
            raise HTTPException(404, f"Server '{server_name}' not found or not running")

        process = server_manager.processes[server_name]

        if process.poll() is not None:
            raise HTTPException(503, f"Server '{server_name}' is not running")

        # ── SSE transport ────────────────────────────────────────────────────
        if isinstance(process, SseSubprocessHandle):
            if "name" not in request_body:
                raise HTTPException(400, "Tool name is required")
            response = await _proxy_to_sse_server(
                process.sse_url,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": request_body
                },
                timeout=60.0
            )
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
            response_line = await _dispatch_stdio(server_name, process, msg)
            response_data = json.loads(response_line)

            # Update last_used_at for idle cleanup
            await server_manager.update_last_used(server_name)

            return JSONResponse(content=response_data)

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error calling tool on '{server_name}': {e}")
            raise HTTPException(500, f"Error communicating with server: {str(e)}")

    return router


if __name__ == '__main__':
    app = FastAPI()
    install_paths = [
        "/workspaces/fluid-ai-gpt-mcp/fluidmcp/.fmcp-packages/Perplexity/perplexity-ask/0.1.0",
        "/workspaces/fluid-ai-gpt-mcp/fluidmcp/.fmcp-packages/Airbnb/airbnb/0.1.0"
    ]
    for install_path in install_paths:
        logger.info(f"Launching MCP server for {install_path}")
        package_name, router = launch_mcp_using_fastapi_proxy(install_path)
        if package_name is not None and router is not None:
            app.include_router(router)
        else:
            logger.warning(f"Skipping {install_path} due to missing metadata or launch error")
    uvicorn.run(app, host="0.0.0.0", port=8099)