import os
import json
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

    def _drain() -> None:
        nonlocal log_fh
        try:
            if process.stderr is None:
                return
            for line in process.stderr:
                stripped = line.rstrip()
                with lock:
                    buf.append(stripped)
                logger.info("[{}] {}", key, stripped)
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


def readline_with_timeout(process: subprocess.Popen, timeout: float = 30.0) -> str:
    """Read one line from process stdout with a timeout.

    Uses select() on Unix so the calling thread is not blocked indefinitely if the
    subprocess hangs. On Windows (where select() doesn't support pipes), falls back
    to a dedicated reader thread with a join timeout. Returns "" on timeout or EOF.
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
    """
    Legacy single-package proxy. Creates a standalone FastAPI app that forwards
    JSON-RPC requests to one MCP subprocess over stdin/stdout.

    Error map (what you'll see in logs → root cause):
      [mcp.process_died]   BrokenPipeError/OSError on stdin write
                           → MCP subprocess crashed or was killed externally.
                             Check OS process table and stderr buffer.
      [mcp.timeout]        readline_with_timeout returned ""
                           → Subprocess is alive but not producing output.
                             Could be a deadlock inside the tool, a blocked DB query,
                             or an API call that never returned.
      [mcp.bad_response]   json.JSONDecodeError on stdout line
                           → Subprocess wrote non-JSON to stdout (e.g. a print()
                             statement, a Python traceback, or a startup banner).
                             Check stderr drainer logs for the actual error.
      [mcp.error_response] JSON-RPC "error" field present in response
                           → Tool executed but returned a protocol-level error.
                             Common causes: DB connection refused, API key invalid,
                             missing required argument, downstream API returned 4xx/5xx.
      [mcp.lock_wait]      process_lock already held when a new request arrives
                           → Two concurrent requests are competing for the same
                             subprocess stdin/stdout pipe (which is single-threaded).
                             One request will queue; high frequency = throughput bottleneck.
    """
    app = FastAPI()
    process_lock = threading.Lock()

    @app.post(f"/{package_name}/mcp")
    async def proxy_jsonrpc(request: Request):
        t0 = time.monotonic()
        raw = await request.body()
        jsonrpc_str = raw.decode() if isinstance(raw, bytes) else raw

        # Best-effort parse for log context — malformed bodies still get forwarded.
        try:
            parsed_req = json.loads(jsonrpc_str)
        except json.JSONDecodeError:
            parsed_req = {}

        method = parsed_req.get("method", "unknown")
        request_id = parsed_req.get("id", "-")
        params = parsed_req.get("params", {})
        tool_name = params.get("name") if method == "tools/call" else None
        # Log argument keys only (not values) to avoid leaking secrets in logs.
        tool_args_keys = sorted(params.get("arguments", {}).keys()) if method == "tools/call" else []

        ctx = f"server={package_name} method={method} req_id={request_id}"
        if tool_name:
            ctx += f" tool={tool_name} args={tool_args_keys}"

        logger.info(f"[mcp.call] {ctx}")

        def _communicate(payload: str) -> str:
            # Non-blocking acquire first; if the lock is taken, log a warning before
            # blocking — this surfaces thread contention without adding overhead on
            # the happy path.
            acquired = process_lock.acquire(blocking=False)
            if not acquired:
                # CAUGHT: [mcp.lock_wait] — concurrent request already using this subprocess.
                # Investigate if you see this frequently; it means requests are serialising
                # and latency will stack.
                logger.warning(f"[mcp.lock_wait] {ctx} — another request holds the process lock, queuing")
                process_lock.acquire()
            try:
                process.stdin.write(payload + "\n")
                process.stdin.flush()
                return readline_with_timeout(process, timeout=30.0)
            finally:
                process_lock.release()

        try:
            response_line = await asyncio.to_thread(_communicate, jsonrpc_str)
        except (BrokenPipeError, OSError) as e:
            # CAUGHT: [mcp.process_died] — stdin write failed.
            # Root cause: subprocess exited (OOM, unhandled exception, SIGKILL).
            # Next step: check `process.returncode` and the stderr drainer buffer
            # for the crash reason.
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.error(f"[mcp.process_died] {ctx} elapsed={elapsed_ms}ms — broken pipe: {e}")
            return JSONResponse(status_code=503, content={"error": f"Process pipe broken: {e}"})

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        if not response_line:
            # CAUGHT: [mcp.timeout] — readline returned "" after 30s.
            # Root cause: tool is blocking (slow DB query, hung HTTP call, infinite loop).
            # Next step: check the tool implementation and any downstream service it calls.
            logger.warning(f"[mcp.timeout] {ctx} elapsed={elapsed_ms}ms — server did not respond within 30s")
            return JSONResponse(status_code=504, content={"error": "MCP server did not respond within timeout"})

        try:
            parsed_resp = json.loads(response_line)
        except json.JSONDecodeError as e:
            # CAUGHT: [mcp.bad_response] — stdout line is not valid JSON.
            # Root cause: tool printed a plain string, Python traceback, or startup
            # message to stdout. Check stderr drainer for the real error.
            logger.error(f"[mcp.bad_response] {ctx} elapsed={elapsed_ms}ms — invalid JSON: {e} raw={response_line[:300]}")
            return JSONResponse(status_code=502, content={"error": "MCP server returned invalid JSON"})

        if "error" in parsed_resp:
            # CAUGHT: [mcp.error_response] — JSON-RPC error object in response body.
            # Root cause varies by error code:
            #   -32700 Parse error        → gateway sent malformed JSON to the tool
            #   -32600 Invalid request    → missing required JSON-RPC fields
            #   -32601 Method not found   → tool name doesn't exist on this server
            #   -32602 Invalid params     → wrong argument types or missing required args
            #   -32603 Internal error     → tool threw an unhandled exception (DB down,
            #                               API timeout, file not found, etc.)
            #   Any other code            → tool-defined application error
            err = parsed_resp["error"]
            err_code = err.get("code") if isinstance(err, dict) else None
            err_msg = err.get("message") if isinstance(err, dict) else str(err)
            logger.warning(f"[mcp.error_response] {ctx} elapsed={elapsed_ms}ms — code={err_code} message={err_msg}")
        else:
            logger.info(f"[mcp.ok] {ctx} elapsed={elapsed_ms}ms")

        return JSONResponse(content=parsed_resp)

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
    

def create_mcp_router(package_name: str, process: subprocess.Popen, process_lock: threading.Lock = None) -> APIRouter:
    """
    Per-package router used by `fmcp run <package>` mode. Attaches to the shared
    FastAPI app with bearer-token auth and Prometheus metrics.

    Error map (what you'll see in logs → root cause):
      [mcp.call]           INFO  — request received; always emitted before any I/O.
      [mcp.stdin]          DEBUG — raw payload sent to subprocess stdin (first 200 chars).
      [mcp.lock_wait]      WARN  — concurrent request is already using this subprocess.
                                   Requests are serialised per-process; high frequency here
                                   means throughput is bottlenecked on a single subprocess.
      [mcp.timeout]        WARN  — subprocess alive but no stdout within 30s.
                                   Root cause: tool blocked on DB, API, or infinite loop.
      [mcp.bad_response]   ERROR — stdout line was not valid JSON.
                                   Root cause: tool wrote a plain string/traceback to stdout.
                                   Check stderr drainer logs for the real error message.
      [mcp.error_response] WARN  — JSON-RPC error in response body (tool ran, but failed).
                                   Common causes by error code:
                                     -32603 Internal error → DB refused connection, API
                                            returned 4xx/5xx, file not found, unhandled exception
                                     -32602 Invalid params → caller sent wrong argument types
                                     -32601 Method not found → tool name doesn't exist
      [mcp.process_died]   ERROR — BrokenPipeError/OSError writing to stdin.
                                   Root cause: subprocess crashed (OOM, SIGKILL, unhandled
                                   exception at top level). Check process.returncode and
                                   stderr drainer buffer for crash details.
      [mcp.error]          ERROR — unexpected exception not covered above (e.g. asyncio
                                   cancellation, memory error, bug in gateway code).
                                   Full traceback is included.
    """

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
        collector = MetricsCollector(package_name)
        method = request.get("method", "unknown")
        request_id = request.get("id", "-")
        params = request.get("params", {})
        tool_name = params.get("name") if method == "tools/call" else None
        # Log argument keys only (not values) to avoid leaking secrets in logs.
        tool_args_keys = sorted(params.get("arguments", {}).keys()) if method == "tools/call" else []

        ctx = f"server={package_name} method={method} req_id={request_id}"
        if tool_name:
            ctx += f" tool={tool_name} args={tool_args_keys}"

        t0 = time.monotonic()

        with RequestTimer(collector, method):
            try:
                all_headers = dict(http_request.headers)

                # LOGGED: [mcp.call] — first thing emitted for every request.
                # If you see [mcp.call] but no [mcp.ok] or error follow-up, the
                # request is still in-flight (or the process crashed with no pipe error).
                logger.info(f"[mcp.call] {ctx}")

                # Inject HTTP headers into tool arguments so downstream tools can
                # forward auth headers (e.g. Authorization, X-Api-Key) to their APIs.
                # Only done for tools/call — list/initialize don't need caller headers.
                if method == "tools/call" and all_headers:
                    if "arguments" not in params:
                        params["arguments"] = {}
                    params["arguments"]["headers"] = all_headers
                    request["params"] = params

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

                msg = json.dumps(request)
                # LOGGED: [mcp.stdin] DEBUG — full payload preview before it enters the pipe.
                # Useful when debugging argument injection or protocol-level mismatches.
                logger.debug(f"[mcp.stdin] {ctx} payload={msg[:200]}")

                def _communicate_mcp(payload: str) -> str:
                    # Non-blocking acquire first; warn before blocking so lock contention
                    # is visible in logs without adding overhead on the happy path.
                    # LOGGED: [mcp.lock_wait] — only when contended.
                    acquired = process_lock.acquire(blocking=False)
                    if not acquired:
                        logger.warning(f"[mcp.lock_wait] {ctx} — another request holds the process lock, queuing")
                        process_lock.acquire()
                    try:
                        process.stdin.write(payload + "\n")
                        process.stdin.flush()
                        return readline_with_timeout(process, timeout=30.0)
                    finally:
                        process_lock.release()

                response_line = await asyncio.to_thread(_communicate_mcp, msg)
                elapsed_ms = int((time.monotonic() - t0) * 1000)

                if not response_line:
                    # CAUGHT: [mcp.timeout] — no output from subprocess within 30s.
                    # Root cause: tool is blocked. Common culprits:
                    #   • Database query with no timeout (connection refused hangs by default)
                    #   • External HTTP API call with no timeout set
                    #   • Tool stuck in a retry loop or waiting on a lock
                    # Next step: check the tool's own logs and any downstream services it calls.
                    logger.warning(f"[mcp.timeout] {ctx} elapsed={elapsed_ms}ms — server did not respond within 30s")
                    return JSONResponse(status_code=504, content={"error": f"[{package_name}] MCP server did not respond within timeout"})

                try:
                    parsed = json.loads(response_line)
                except json.JSONDecodeError as e:
                    # CAUGHT: [mcp.bad_response] — stdout line is not valid JSON.
                    # Root cause: tool wrote a plain-text message, Python traceback,
                    # or startup banner to stdout instead of stderr.
                    # Next step: look at stderr drainer logs ([{package_name}] stderr:)
                    # for the actual error text.
                    logger.error(f"[mcp.bad_response] {ctx} elapsed={elapsed_ms}ms — invalid JSON: {e} raw={response_line[:300]}")
                    return JSONResponse(status_code=502, content={"error": "MCP server returned invalid JSON"})

                if "error" in parsed:
                    # CAUGHT: [mcp.error_response] — tool ran but returned a JSON-RPC error.
                    # The tool itself is alive and responding; the error is application-level.
                    # Error code guide:
                    #   -32603 Internal error  → unhandled exception inside the tool
                    #                            (DB down, API 5xx, missing env var, etc.)
                    #   -32602 Invalid params  → caller passed wrong types or missing args
                    #   -32601 Method not found → wrong tool name in the request
                    #   -32700 Parse error     → gateway sent malformed JSON (should not happen)
                    #   Custom codes           → tool-defined errors (check tool docs)
                    err = parsed["error"]
                    err_code = err.get("code") if isinstance(err, dict) else None
                    err_msg = err.get("message") if isinstance(err, dict) else str(err)
                    logger.warning(f"[mcp.error_response] {ctx} elapsed={elapsed_ms}ms — code={err_code} message={err_msg}")
                else:
                    logger.info(f"[mcp.ok] {ctx} elapsed={elapsed_ms}ms")

                return JSONResponse(content=parsed)

            except (BrokenPipeError, OSError) as e:
                # CAUGHT: [mcp.process_died] — stdin write raised a pipe error.
                # Root cause: subprocess exited unexpectedly.
                # Next step: check process.returncode and stderr drainer buffer for
                # the crash reason (OOM kill, unhandled top-level exception, etc.).
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                logger.error(f"[mcp.process_died] {ctx} elapsed={elapsed_ms}ms — broken pipe: {e}")
                collector.record_error("process_died")
                return JSONResponse(status_code=503, content={"error": f"MCP process died: {e}"})
            except Exception as e:
                # CAUGHT: [mcp.error] — unexpected exception not covered above.
                # Could be: asyncio.CancelledError, MemoryError, bug in gateway code,
                # or an exception raised inside asyncio.to_thread's worker.
                # Full traceback is logged; inspect exc_info for details.
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                logger.error(f"[mcp.error] {ctx} elapsed={elapsed_ms}ms — {type(e).__name__}: {e}", exc_info=True)
                return JSONResponse(status_code=500, content={"error": str(e)})
    
    # SSE endpoint — used by clients that want streaming responses over a persistent connection.
    # Unlike the /mcp endpoint (request→response), SSE streams multiple chunks until the tool
    # signals completion with a "result" field.
    #
    # Error map for SSE (what you'll see in logs → root cause):
    #   [mcp.sse.start]          INFO  — connection opened; always emitted first.
    #   [mcp.sse.chunk]          DEBUG — each JSON chunk received from subprocess stdout.
    #   [mcp.sse.timeout]        WARN  — readline returned "" (no data within 30s).
    #                                    Root cause: tool stalled mid-stream. Could be a
    #                                    slow API page, DB cursor stall, or generator paused.
    #   [mcp.sse.error_response] WARN  — tool sent a JSON-RPC error chunk mid-stream.
    #                                    Root cause: same as [mcp.error_response] above.
    #                                    Stream is still forwarded to the client.
    #   [mcp.sse.ok]             INFO  — final "result" chunk received; stream completed.
    #   [mcp.sse.process_died]   ERROR — BrokenPipeError writing to stdin.
    #                                    Root cause: subprocess crashed while streaming.
    #                                    Check process.returncode and stderr drainer buffer.
    #   [mcp.sse.error]          ERROR — unexpected exception inside the generator.
    #                                    Full traceback included.
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
        sse_method = request.get("method", "unknown")
        sse_request_id = request.get("id", "-")
        sse_params = request.get("params", {})
        sse_tool_name = sse_params.get("name") if sse_method == "tools/call" else None
        # Log argument keys only (not values) to avoid leaking secrets in logs.
        sse_tool_args_keys = sorted(sse_params.get("arguments", {}).keys()) if sse_method == "tools/call" else []

        sse_ctx = f"server={package_name} method={sse_method} req_id={sse_request_id}"
        if sse_tool_name:
            sse_ctx += f" tool={sse_tool_name} args={sse_tool_args_keys}"

        all_headers = dict(http_request.headers)

        # Inject caller HTTP headers into tool arguments so downstream tools can
        # forward auth tokens to their own APIs (same as the /mcp endpoint).
        if sse_method == "tools/call" and all_headers:
            if "arguments" not in sse_params:
                sse_params["arguments"] = {}
            sse_params["arguments"]["headers"] = all_headers
            request["params"] = sse_params

        collector = MetricsCollector(package_name)

        async def event_generator() -> AsyncIterator[str]:
            completion_status = "success"
            t0 = time.monotonic()
            try:
                collector.increment_active_streams()
                # LOGGED: [mcp.sse.start] — connection established, about to write to stdin.
                logger.info(f"[mcp.sse.start] {sse_ctx}")

                msg = json.dumps(request)

                def _send_request(payload: str) -> None:
                    with process_lock:
                        process.stdin.write(payload + "\n")
                        process.stdin.flush()

                await asyncio.to_thread(_send_request, msg)

                chunk_count = 0
                while True:
                    response_line = await asyncio.to_thread(readline_with_timeout, process, 30.0)
                    if not response_line:
                        # CAUGHT: [mcp.sse.timeout] — no chunk arrived within 30s.
                        # Root cause: generator inside the tool paused or stalled.
                        # Could be a slow paginated API, a DB cursor that stopped
                        # yielding, or the tool waiting on an external event.
                        elapsed_ms = int((time.monotonic() - t0) * 1000)
                        logger.warning(f"[mcp.sse.timeout] {sse_ctx} elapsed={elapsed_ms}ms chunks_received={chunk_count}")
                        break

                    chunk_count += 1
                    # LOGGED: [mcp.sse.chunk] DEBUG — each individual chunk from stdout.
                    logger.debug(f"[mcp.sse.chunk] {sse_ctx} chunk={chunk_count} data={response_line.strip()[:200]}")
                    yield f"data: {response_line.strip()}\n\n"

                    try:
                        response_data = json.loads(response_line)
                        if "error" in response_data:
                            # CAUGHT: [mcp.sse.error_response] — tool sent an error chunk.
                            # The stream is still forwarded to the client so it can handle
                            # the error. Root cause: same as [mcp.error_response] on /mcp.
                            err = response_data["error"]
                            err_code = err.get("code") if isinstance(err, dict) else None
                            err_msg = err.get("message") if isinstance(err, dict) else str(err)
                            elapsed_ms = int((time.monotonic() - t0) * 1000)
                            logger.warning(f"[mcp.sse.error_response] {sse_ctx} elapsed={elapsed_ms}ms code={err_code} message={err_msg}")
                            completion_status = "error_response"
                        if "result" in response_data:
                            # LOGGED: [mcp.sse.ok] — tool signalled completion normally.
                            elapsed_ms = int((time.monotonic() - t0) * 1000)
                            logger.info(f"[mcp.sse.ok] {sse_ctx} elapsed={elapsed_ms}ms chunks={chunk_count}")
                            break
                    except json.JSONDecodeError:
                        # Non-JSON lines are silently forwarded — some tools stream
                        # progress text before the final JSON result.
                        pass

            except (BrokenPipeError, OSError) as e:
                # CAUGHT: [mcp.sse.process_died] — subprocess exited while streaming.
                # Root cause: OOM kill, unhandled exception, or SIGKILL during a long
                # streaming operation. Check process.returncode and stderr drainer buffer.
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                completion_status = "broken_pipe"
                collector.record_error("process_died")
                logger.error(f"[mcp.sse.process_died] {sse_ctx} elapsed={elapsed_ms}ms — broken pipe: {e}")
                yield f"data: {json.dumps({'error': f'Process pipe broken: {str(e)}'})}\n\n"
            except Exception as e:
                # CAUGHT: [mcp.sse.error] — unexpected exception inside the generator.
                # Could be an asyncio.CancelledError (client disconnected), MemoryError,
                # or a bug in gateway code. Full traceback is included.
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                completion_status = "error"
                logger.error(f"[mcp.sse.error] {sse_ctx} elapsed={elapsed_ms}ms — {type(e).__name__}: {e}", exc_info=True)
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
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
                        return readline_with_timeout(process, timeout=30.0)

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
                        return readline_with_timeout(process, timeout=30.0)

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
        method = request.get("method", "unknown")

        # RequestTimer automatically records error_type="network_error" for HTTPExceptions
        # via RequestTimer.__exit__ → _categorize_error() → name-based matching.
        params = request.get("params", {})
        tool_name = params.get("name") if method == "tools/call" else None
        # Log argument keys only (not values) to avoid leaking secrets in logs.
        tool_args_keys = sorted(params.get("arguments", {}).keys()) if method == "tools/call" else []
        request_id = request.get("id", "-")

        ctx = f"server={server_name} method={method} req_id={request_id}"
        if tool_name:
            ctx += f" tool={tool_name} args={tool_args_keys}"

        t0 = time.monotonic()

        with RequestTimer(collector, method):
            # CAUGHT: [mcp.not_found] — server not in the live process registry.
            # Could mean: server never started, startup failed, or idle-timeout evicted it.
            if server_name not in server_manager.processes:
                logger.warning(f"[mcp.not_found] {ctx} — server not registered")
                raise HTTPException(404, f"Server '{server_name}' not found or not running")

            process = server_manager.processes[server_name]

            # CAUGHT: [mcp.process_dead] — process exited before this request arrived.
            # Attaches stderr tail so you can see the crash reason without digging through files.
            if process.poll() is not None:
                stderr_tail = get_stderr_tail(server_name, 20)
                logger.error(
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
            logger.info(f"[mcp.call] {ctx}")

            # ── SSE transport: server is an HTTP-based SSE subprocess, not a stdio process.
            # Forward the request over HTTP instead of stdin/stdout.
            if isinstance(process, SseSubprocessHandle):
                with RequestTimer(collector, request.get("method", "unknown")):
                    response = await _proxy_to_sse_server(process.sse_url, request)
                    elapsed_ms = int((time.monotonic() - t0) * 1000)
                    logger.info(f"[mcp.ok] {ctx} elapsed={elapsed_ms}ms transport=sse_http")
                    return JSONResponse(content=response)
            # ── stdio transport: write to stdin, read from stdout ────────────

            try:
                msg = json.dumps(request)
                try:
                    process.stdin.write(msg + "\n")
                    process.stdin.flush()
                except (BrokenPipeError, OSError) as e:
                    # CAUGHT: [mcp.process_died] — stdin write failed mid-request.
                    # Root cause: subprocess crashed between process.poll() check above
                    # and this write. Attaches stderr tail for crash diagnosis.
                    elapsed_ms = int((time.monotonic() - t0) * 1000)
                    stderr_tail = get_stderr_tail(server_name, 20)
                    logger.error(
                        f"[mcp.process_died] {ctx} elapsed={elapsed_ms}ms — broken pipe: {e}"
                        + (f"\nstderr:\n{stderr_tail}" if stderr_tail else "")
                    )
                    raise HTTPException(503, f"Server '{server_name}' process pipe broken: {str(e)}")

                # readline_with_timeout uses select() internally so this thread returns
                # after 30s instead of blocking forever (no stuck asyncio worker threads).
                response_line = await asyncio.to_thread(readline_with_timeout, process, 30.0)
                elapsed_ms = int((time.monotonic() - t0) * 1000)

                if not response_line:
                    # CAUGHT: [mcp.timeout] — subprocess alive but produced no output in 30s.
                    # Root cause: tool is blocking on a slow operation. Common causes:
                    #   • DB connection with no query timeout (hangs indefinitely on refusal)
                    #   • HTTP call to an API with no timeout set
                    #   • Tool waiting on a lock or resource held by another process
                    logger.warning(f"[mcp.timeout] {ctx} elapsed={elapsed_ms}ms — server did not respond within 30s")
                    raise HTTPException(504, f"Server '{server_name}' timed out responding")

                # LOGGED: [mcp.slow] — response arrived but took over 5s.
                # Not an error but a leading indicator that the downstream is degraded.
                if elapsed_ms > 5000:
                    logger.warning(f"[mcp.slow] {ctx} elapsed={elapsed_ms}ms — response was slow")

                try:
                    response_data = json.loads(response_line)
                except json.JSONDecodeError as e:
                    # CAUGHT: [mcp.bad_response] — stdout line is not valid JSON.
                    # Root cause: tool printed a plain-text error, Python traceback,
                    # or startup message to stdout instead of stderr.
                    # Next step: look at stderr drainer logs for the real error text.
                    logger.error(f"[mcp.bad_response] {ctx} elapsed={elapsed_ms}ms — invalid JSON: {e} raw={response_line[:300]}")
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
                    err_msg = err.get("message") if isinstance(err, dict) else str(err)
                    logger.warning(f"[mcp.error_response] {ctx} elapsed={elapsed_ms}ms — code={err_code} message={err_msg}")
                else:
                    logger.info(f"[mcp.ok] {ctx} elapsed={elapsed_ms}ms")

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
                logger.error(f"[mcp.error] {ctx} elapsed={elapsed_ms}ms — {type(e).__name__}: {e}", exc_info=True)
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

                msg = json.dumps(request)
                try:
                    process.stdin.write(msg + "\n")
                    process.stdin.flush()
                except (BrokenPipeError, OSError) as e:
                    # CAUGHT: broken_pipe on stdin write at stream start.
                    # completion_status intentionally differs from fluidmcp_errors_total
                    # error_type="io_error": the metrics label tracks how the stream
                    # *ended* (for per-stream analysis), while the counter tracks the
                    # global rate of I/O failures (for alerting). Same root cause,
                    # different observability scope.
                    completion_status = "broken_pipe"
                    collector.record_error("io_error")
                    yield f"data: {json.dumps({'error': f'Process pipe broken: {str(e)}'})}\n\n"
                    return

                sse_method = request.get("method", "unknown")
                sse_params = request.get("params", {})
                sse_tool_name = sse_params.get("name") if sse_method == "tools/call" else None
                # Log argument keys only (not values) to avoid leaking secrets in logs.
                sse_tool_args_keys = sorted(sse_params.get("arguments", {}).keys()) if sse_method == "tools/call" else []
                sse_ctx = f"server={server_name} method={sse_method} req_id={request.get('id', '-')}"
                if sse_tool_name:
                    sse_ctx += f" tool={sse_tool_name} args={sse_tool_args_keys}"
                t0_sse = time.monotonic()
                chunk_count = 0

                # LOGGED: [mcp.sse.start] — stdin write succeeded; reading loop begins.
                logger.info(f"[mcp.sse.start] {sse_ctx}")

                while True:
                    response_line = await asyncio.to_thread(readline_with_timeout, process, 30.0)
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
                        # Process is alive but produced nothing in 30s — send a keep-alive
                        # SSE comment to prevent the client from closing the connection.
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
                            err_msg = err.get("message") if isinstance(err, dict) else str(err)
                            elapsed_ms = int((time.monotonic() - t0_sse) * 1000)
                            logger.warning(f"[mcp.sse.error_response] {sse_ctx} elapsed={elapsed_ms}ms code={err_code} message={err_msg}")
                            completion_status = "error_response"
                        if "result" in response_data:
                            # LOGGED: [mcp.sse.ok] — tool completed normally.
                            elapsed_ms = int((time.monotonic() - t0_sse) * 1000)
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
            try:
                process.stdin.write(msg + "\n")
                process.stdin.flush()
            except (BrokenPipeError, OSError) as e:
                raise HTTPException(503, f"Server '{server_name}' process pipe broken: {str(e)}")

            # Non-blocking I/O — readline_with_timeout uses select() so the thread
            # returns after 30s instead of blocking forever (no stuck threads).
            response_line = await asyncio.to_thread(readline_with_timeout, process, 30.0)
            if not response_line:
                raise HTTPException(504, f"Server '{server_name}' timed out responding")
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
            try:
                process.stdin.write(msg + "\n")
                process.stdin.flush()
            except (BrokenPipeError, OSError) as e:
                raise HTTPException(503, f"Server '{server_name}' process pipe broken: {str(e)}")

            # Tool execution with timeout — readline_with_timeout uses select() so the
            # thread returns after 60s instead of blocking forever (no stuck threads).
            response_line = await asyncio.to_thread(readline_with_timeout, process, 60.0)
            if not response_line:
                # Log timeout failure
                await server_manager.db.save_log_entry({
                    "server_name": server_name,
                    "stream": "error",
                    "content": f"Tool '{request_body.get('name', 'unknown')}' execution timed out after 60 seconds"
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