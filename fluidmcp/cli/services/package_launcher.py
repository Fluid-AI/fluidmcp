import os
import json
import subprocess
import shutil
import asyncio
import time
import threading
from typing import Union, Dict, Any, Iterator, AsyncIterator
from pathlib import Path
from loguru import logger
from fastapi import Request, APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..utils.env_utils import is_placeholder
from .metrics import MetricsCollector, RequestTimer
from .sse_handle import SseSubprocessHandle

security = HTTPBearer(auto_error=False)

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

            # ── SSE transport: forward via HTTP ─────────────────────────────
            if isinstance(process, SseSubprocessHandle):
                with RequestTimer(collector, request.get("method", "unknown")):
                    response = await _proxy_to_sse_server(process.sse_url, request)
                    return JSONResponse(content=response)
            # ── stdio transport continues below ─────────────────────────────

            try:
                # Send request to MCP server
                msg = json.dumps(request)
                async with _get_io_lock(server_name):
                    try:
                        process.stdin.write(msg + "\n")
                        process.stdin.flush()
                    except (BrokenPipeError, OSError) as e:
                        raise HTTPException(503, f"Server '{server_name}' process pipe broken: {str(e)}")

                    # Read response (non-blocking with asyncio.to_thread)
                    response_line = await asyncio.to_thread(process.stdout.readline)
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
                    return  # done for SSE — don't fall through to stdin path
                # ── stdio transport continues below ──────────────────────────

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
                        completion_status = "broken_pipe"
                        # Record in global error metric for monitoring
                        collector.record_error("io_error")
                        yield f"data: {json.dumps({'error': f'Process pipe broken: {str(e)}'})}\n\n"
                        return

                while True:
                    # Non-blocking I/O with asyncio.to_thread
                    response_line = await asyncio.to_thread(process.stdout.readline)
                    if not response_line:
                        break

                    logger.debug(f"Received from MCP: {response_line.strip()}")
                    yield f"data: {response_line.strip()}\n\n"

                    # Check if response is final
                    try:
                        response_data = json.loads(response_line)
                        if "result" in response_data:
                            break
                    except json.JSONDecodeError:
                        # Non-JSON lines are expected in the stream; ignore them but continue reading
                        logger.debug(f"Ignoring non-JSON MCP response line: {response_line.strip()}")

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
            async with _get_io_lock(server_name):
                try:
                    process.stdin.write(msg + "\n")
                    process.stdin.flush()
                except (BrokenPipeError, OSError) as e:
                    raise HTTPException(503, f"Server '{server_name}' process pipe broken: {str(e)}")

                # Non-blocking I/O with asyncio.to_thread
                response_line = await asyncio.to_thread(process.stdout.readline)
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
            async with _get_io_lock(server_name):
                try:
                    process.stdin.write(msg + "\n")
                    process.stdin.flush()
                except (BrokenPipeError, OSError) as e:
                    raise HTTPException(503, f"Server '{server_name}' process pipe broken: {str(e)}")

                # Tool execution with timeout
                try:
                    response_line = await asyncio.wait_for(
                        asyncio.to_thread(process.stdout.readline),
                        timeout=60.0  # 60 second tool execution timeout
                    )
                except asyncio.TimeoutError:
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
