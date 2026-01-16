import os
import json
import subprocess
import shutil
import asyncio
import time
import sys
import threading
from typing import Union, Dict, Any, Iterator, AsyncIterator
from pathlib import Path
from loguru import logger
from fastapi import FastAPI, Request, APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn

security = HTTPBearer(auto_error=False)

def is_placeholder_value(value: str) -> bool:
    """
    Detect if an environment variable value is a placeholder.

    Common placeholder patterns:
    - Contains angle brackets: <your-username>, <password>
    - Contains 'xxxx' pattern: xxxx.databases.neo4j.io
    - Contains 'placeholder' keyword
    - Generic patterns: 'your-*', 'my-*'

    Args:
        value: The environment variable value to check

    Returns:
        True if the value appears to be a placeholder, False otherwise
    """
    if not isinstance(value, str):
        return False

    placeholder_indicators = [
        '<' in value and '>' in value,  # <your-username>
        'xxxx' in value.lower(),         # xxxx.example.com
        'placeholder' in value.lower(),  # placeholder-value
        value.startswith('<') and value.endswith('>'),
        'your-' in value.lower(),        # your-password
        'my-' in value.lower(),          # my-api-key
    ]

    return any(placeholder_indicators)

def get_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate bearer token if secure mode is enabled"""
    bearer_token = os.environ.get("FMCP_BEARER_TOKEN")
    secure_mode = os.environ.get("FMCP_SECURE_MODE") == "true"
    
    if not secure_mode:
        return None
    if not credentials or credentials.scheme.lower() != "bearer" or credentials.credentials != bearer_token:
        raise HTTPException(status_code=401, detail="Invalid or missing authorization token")
    return credentials.credentials

def launch_mcp_using_fastapi_proxy(dest_dir: Union[str, Path]):
    """
    Launch an MCP server and create a FastAPI router for it.

    Args:
        dest_dir: Path to the package installation directory

    Returns:
        Tuple of (package_name, router, process) or (None, None, None) on failure
    """
    dest_dir = Path(dest_dir)
    metadata_path = dest_dir / "metadata.json"

    try:
        if not metadata_path.exists():
            logger.warning(f"No metadata.json found at {metadata_path}")
            return None, None, None
        logger.info(f"Reading metadata.json from {metadata_path}")
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        pkg = list(metadata["mcpServers"].keys())[0]
        servers = metadata['mcpServers'][pkg]
        logger.debug(f"Package: {pkg}, Servers: {servers}")
    except Exception:
        logger.exception("Error reading metadata.json")
        return None, None, None

    def replace_path_placeholders(arg: str, dest_dir: Path) -> str:
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
            result = result.replace(placeholder, str(dest_dir))
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
                if is_placeholder_value(value):
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

        # Determine working directory based on package type
        is_github_repo = (dest_dir / ".git").exists()

        if is_github_repo:
            # GitHub repository
            if base_command in ["npx", str(shutil.which("npx"))] and "-y" in args:
                # npx -y: run from parent to avoid package.json conflicts
                working_dir = dest_dir.parent
                logger.info(f"GitHub repo with npx -y: using parent directory {working_dir}")
            else:
                # Source code or local installation: use repo directory
                working_dir = dest_dir
                logger.info(f"GitHub repo with source: using repo directory {working_dir}")
        else:
            # Registry package or direct config: use package directory
            working_dir = dest_dir

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

        router = create_mcp_router(pkg, process)
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
    @app.post(f"/{package_name}/mcp")
    async def proxy_jsonrpc(request: Request):
        try:
            jsonrpc_request = await request.body()
            jsonrpc_str = jsonrpc_request.decode() if isinstance(jsonrpc_request, bytes) else jsonrpc_request
            # Send to MCP server via stdin
            process.stdin.write(jsonrpc_str + "\n")
            process.stdin.flush()
            # Read from MCP server stdout
            response_line = process.stdout.readline()
            return JSONResponse(content=json.loads(response_line))
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
    return app


def start_fastapi_in_thread(app: FastAPI, port: int):
    def run():
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    thread = threading.Thread(target=run, daemon=True)
    thread.start()


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
            pass

        return False
    except Exception:
        logger.exception("Initialization error")
        return False
    

def create_mcp_router(package_name: str, process: subprocess.Popen) -> APIRouter:
    router = APIRouter()

    @router.post(f"/{package_name}/mcp", tags=[package_name])
    async def proxy_jsonrpc(
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
        try:
            # Convert dict to JSON string
            msg = json.dumps(request)
            process.stdin.write(msg + "\n")
            process.stdin.flush()
            response_line = process.stdout.readline()
            return JSONResponse(content=json.loads(response_line))
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
    
    # New SSE endpoint
    @router.post(f"/{package_name}/sse", tags=[package_name])
    async def sse_stream(
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
        async def event_generator() -> Iterator[str]:
            try:
                # Convert dict to JSON string and send to MCP server
                msg = json.dumps(request)
                process.stdin.write(msg + "\n")
                process.stdin.flush()
                
                # Read from stdout and stream as SSE events
                while True:
                    response_line = process.stdout.readline()
                    if not response_line:
                        break
                    
                    # Add logging
                    logger.debug(f"Received from MCP: {response_line.strip()}")
                    
                    # Format as SSE event
                    yield f"data: {response_line.strip()}\n\n"
                    
                    # Check if response contains "result" which indicates completion
                    try:
                        response_data = json.loads(response_line)
                        if "result" in response_data:
                            # If it's a final result, we can stop the stream
                            break
                    except json.JSONDecodeError:
                        # If it's not valid JSON, just stream it as-is
                        pass
                    
            except Exception as e:
                # Send error as SSE event
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )
        
    @router.get(f"/{package_name}/mcp/tools/list", tags=[package_name])
    async def list_tools(token: str = Depends(get_token)):
        try:
            # Pre-filled JSON-RPC request for tools/list
            request_payload = {
                "id": 1,
                "jsonrpc": "2.0",
                "method": "tools/list"
            }
            
            # Convert to JSON string and send to MCP server
            msg = json.dumps(request_payload)
            process.stdin.write(msg + "\n")
            process.stdin.flush()
            
            # Read response from MCP server
            response_line = process.stdout.readline()
            response_data = json.loads(response_line)
            
            return JSONResponse(content=response_data)
            
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
        
    
    @router.post(f"/{package_name}/mcp/tools/call", tags=[package_name])
    async def call_tool(request_body: Dict[str, Any] = Body(
        ...,
        alias="params",
        example={
            "name": "", 
        }
    ), token: str = Depends(get_token)
):      
        params = request_body

        try:
            # Validate required fields
            if "name" not in params:
                return JSONResponse(
                    status_code=400, 
                    content={"error": "Tool name is required"}
                )
            
            # Construct complete JSON-RPC request
            request_payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": params
            }
            
            # Send to MCP server
            msg = json.dumps(request_payload)
            process.stdin.write(msg + "\n")
            process.stdin.flush()
            
            # Read response
            response_line = process.stdout.readline()
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
    from fastapi import HTTPException
    from typing import Iterator
    from .metrics import MetricsCollector, RequestTimer

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

        # Track request with metrics (includes pre-validation errors)
        with RequestTimer(collector, method):
            # Check if server exists
            if server_name not in server_manager.processes:
                collector.record_error("server_not_found")
                raise HTTPException(404, f"Server '{server_name}' not found or not running")

            process = server_manager.processes[server_name]

            # Check if process is alive
            if process.poll() is not None:
                collector.record_error("process_dead")
                raise HTTPException(503, f"Server '{server_name}' is not running (process died)")

            try:
                # Send request to MCP server
                msg = json.dumps(request)
                try:
                    process.stdin.write(msg + "\n")
                    process.stdin.flush()
                except (BrokenPipeError, OSError) as e:
                    collector.record_error("broken_pipe")
                    raise HTTPException(503, f"Server '{server_name}' process pipe broken: {str(e)}")

                # Read response (non-blocking with asyncio.to_thread)
                response_line = await asyncio.to_thread(process.stdout.readline)
                return JSONResponse(content=json.loads(response_line))

            except HTTPException:
                raise
            except Exception as e:
                collector.record_error("communication_error")
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
        # Initialize metrics collector
        collector = MetricsCollector(server_name)

        if server_name not in server_manager.processes:
            collector.record_error("server_not_found")
            raise HTTPException(404, f"Server '{server_name}' not found or not running")

        process = server_manager.processes[server_name]

        if process.poll() is not None:
            collector.record_error("process_dead")
            raise HTTPException(503, f"Server '{server_name}' is not running")

        # Track streaming session
        collector.increment_active_streams()

        async def event_generator() -> AsyncIterator[str]:
            completion_status = "success"
            try:
                msg = json.dumps(request)
                try:
                    process.stdin.write(msg + "\n")
                    process.stdin.flush()
                except (BrokenPipeError, OSError) as e:
                    completion_status = "broken_pipe"
                    collector.record_error("broken_pipe")
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
                collector.record_error("stream_error")
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

            # Non-blocking I/O with asyncio.to_thread
            response_line = await asyncio.to_thread(process.stdout.readline)
            response_data = json.loads(response_line)

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
