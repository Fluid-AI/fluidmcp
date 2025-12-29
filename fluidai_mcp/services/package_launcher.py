import os
import json
import subprocess
import shutil
import time
from typing import Union, Dict, Any, Iterator, Optional
from pathlib import Path

from loguru import logger
from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import requests


security = HTTPBearer(auto_error=False)

# Global reference to thread manager (set by CLI)
_global_thread_manager = None


def set_global_thread_manager(manager):
    """
    Stores thread manager reference globally for health checks.
    Required because health check functions need access to restart threads.
    """
    global _global_thread_manager
    _global_thread_manager = manager


def get_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Validate bearer token when secure mode is enabled.
    Returns None if secure mode is off, raises 401 if token is invalid.
    """
    bearer_token = os.environ.get("FMCP_BEARER_TOKEN")
    secure_mode = os.environ.get("FMCP_SECURE_MODE") == "true"
    
    if not secure_mode:
        return None
    if not credentials or credentials.scheme.lower() != "bearer" or credentials.credentials != bearer_token:
        raise HTTPException(status_code=401, detail="Invalid or missing authorization token")
    return credentials.credentials


def launch_mcp_using_fastapi_proxy(dest_dir: Union[str, Path]):
    """
    Launch MCP server subprocess and create router for direct STDIO communication.
    Returns (package_name, router, process) for use in thread's mini-FastAPI.
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
        
    except Exception as e:
        logger.error(f"Error reading metadata.json: {e}")
        return None, None, None

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

        args = [arg.replace("<path to mcp-servers>", str(dest_dir)) for arg in raw_args]
        stdio_command = [base_command] + args
        env_vars = servers.get("env", {})
        env = {**dict(os.environ), **env_vars}

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
            text=True,
            bufsize=1
        )

        # Initialize MCP server
        if not initialize_mcp_server(process, pkg):
            logger.warning(f"Failed to initialize MCP server for {pkg}")

        router = create_mcp_router(pkg, process)
        return pkg, router, process

    except FileNotFoundError as e:
        logger.error(f"Command not found: {e}")
        return None, None, None
    except Exception as e:
        logger.error(f"Error launching MCP server: {e}")
        return None, None, None


def initialize_mcp_server(process: subprocess.Popen, pkg_name: str = "server", timeout=90) -> bool:
    """
    Initialize MCP server with proper handshake.

    Uses non-blocking I/O with select() to ensure timeout enforcement works reliably
    across all platforms. This prevents indefinite hangs during initialization and
    provides fast feedback when servers fail to start properly. Falls back to
    blocking I/O on systems without select support (e.g., Windows with pipes).

    Args:
        process: The MCP server subprocess to initialize
        pkg_name: Package name for logging context (default: "server")
        timeout: Maximum seconds to wait for initialization (default: 90)

    Returns:
        bool: True if server initialized successfully, False on timeout or failure
    """
    # Check select availability once
    try:
        import select
        has_select = hasattr(select, 'select')
    except ImportError:
        has_select = False
    
    # Send initialization request
    init_request = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"roots": {"listChanged": True}, "sampling": {}},
            "clientInfo": {"name": "fluidmcp-client", "version": "1.0.0"}
        }
    }
    
    try:
        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Check if process died
            if process.poll() is not None:
                logger.error(f"MCP server '{pkg_name}' died during initialization")
                return False
            
            if has_select:
                # Non-blocking I/O with select
                ready_read, _, _ = select.select(
                    [process.stdout, process.stderr], [], [], 0.1
                )
                
                # Log errors from stderr
                if process.stderr in ready_read:
                    stderr_line = process.stderr.readline()
                    if stderr_line:
                        logger.error(f"MCP server '{pkg_name}': {stderr_line.strip()}")
                
                # Check for initialization response
                if process.stdout in ready_read:
                    response_line = process.stdout.readline()
                    if response_line:
                        response = json.loads(response_line)
                        if response.get("id") == 0 and "result" in response:
                            # Send initialized notification
                            notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
                            process.stdin.write(json.dumps(notif) + "\n")
                            process.stdin.flush()
                            logger.info(f"MCP server '{pkg_name}' initialized successfully")
                            return True
            else:
                # Fallback for systems without select
                response_line = process.stdout.readline().strip()
                if response_line:
                    response = json.loads(response_line)
                    if response.get("id") == 0 and "result" in response:
                        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
                        process.stdin.write(json.dumps(notif) + "\n")
                        process.stdin.flush()
                        logger.info(f"MCP server '{pkg_name}' initialized successfully")
                        return True
            
            time.sleep(0.1)
        
        logger.error(f"MCP server '{pkg_name}' initialization timed out after {timeout}s")
        return False
        
    except Exception as e:
        logger.error(f"Failed to initialize MCP server '{pkg_name}': {e}")
        return False


def create_mcp_router(package_name: str, process: subprocess.Popen) -> APIRouter:
    """
    Create router with direct STDIO access to MCP subprocess.
    Used in thread's mini-FastAPI (ports 8100-8900) for actual MCP communication.
    """
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
        ), 
        token: str = Depends(get_token)
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
        ), 
        token: str = Depends(get_token)
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


def check_service_health(package_name: str, service_url: str) -> bool:
    """
    Check if MCP service is healthy, restart thread if dead.
    Raises HTTPException if restart fails.
    """
    global _global_thread_manager
    
    if _global_thread_manager is None:
        logger.error("No global thread manager available")
        raise HTTPException(status_code=503, detail="Thread manager not initialized")
    
    try:
        response = requests.get(f"{service_url}/health", timeout=20)
        
        if response.status_code != 200:
            logger.error(f"Health check failed for {package_name} - HTTP {response.status_code}")

            old_thread = _global_thread_manager.get_thread(package_name)
            if old_thread:
                dest_dir = old_thread.dest_dir
                logger.info(f"Attempting to restart {package_name}")
                
                success = _global_thread_manager.restart_mcp_thread(package_name, dest_dir)
                
                if success:
                    logger.info(f"Successfully restarted {package_name}")
                    return True
                else:
                    logger.error(f"Restart failed for {package_name}")
            
            raise HTTPException(status_code=503, detail=f"Service restart failed for {package_name}")
        
        logger.info(f"Health check passed for {package_name}")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Cannot reach {package_name} health endpoint: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Cannot reach {package_name} service")


def _proxy_request_with_retry(
    package_name: str,
    endpoint: str,
    method: str,
    request_body: Optional[Dict[str, Any]] = None,
    timeout: int = 180
) -> JSONResponse:
    """
    Helper function to proxy requests with health check and auto-retry on failure.

    Args:
        package_name: Name of the MCP package
        endpoint: Full endpoint path (e.g., "package/mcp" or "package/mcp/tools/list")
        method: HTTP method ("GET" or "POST")
        request_body: Optional request body for POST requests
        timeout: Request timeout in seconds

    Returns:
        JSONResponse with the proxied response

    Raises:
        HTTPException: If service restart fails or request cannot be completed
    """
    logger.info(f"Request received for /{endpoint}")

    service_url = _global_thread_manager.get_service_url(package_name)
    logger.info(f"Using service URL: {service_url}")

    check_service_health(package_name, service_url)

    # Build full URL
    full_url = f"{service_url}/{endpoint}"

    try:
        # Initial request
        if method == "GET":
            response = requests.get(full_url, timeout=timeout)
        elif method == "POST":
            response = requests.post(full_url, json=request_body, timeout=timeout)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        response.raise_for_status()
        return JSONResponse(content=response.json())

    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
        logger.error(f"Service error for {package_name}: {str(e)}")

        # Attempt restart and retry
        old_thread = _global_thread_manager.get_thread(package_name)
        if old_thread:
            success = _global_thread_manager.restart_mcp_thread(package_name, old_thread.dest_dir)
            if success:
                new_service_url = _global_thread_manager.get_service_url(package_name)
                logger.info(f"Service restarted, waiting for initialization...")
                time.sleep(1)  # Allow new service to fully initialize
                logger.info(f"Retrying with new URL: {new_service_url}")

                # Retry with new URL
                new_full_url = f"{new_service_url}/{endpoint}"
                if method == "GET":
                    response = requests.get(new_full_url, timeout=timeout)
                elif method == "POST":
                    response = requests.post(new_full_url, json=request_body, timeout=timeout)

                return JSONResponse(content=response.json())

        raise HTTPException(status_code=503, detail=f"Service restart failed for {package_name}")


def create_proxy_mcp_router(package_name: str, service_url: str, secure_mode: bool = False):
    """
    Create proxy router that forwards requests to mini-FastAPI with health checks.
    Used in main proxy (port 8099) to route requests to thread-specific services.
    """
    router = APIRouter()
    
    @router.get(f"/{package_name}/health", tags=[package_name])
    def proxy_health_check(token: str = Depends(get_token)):
        """Proxy the health check to the mini-FastAPI"""
        service_url = _global_thread_manager.get_service_url(package_name)
        logger.info(f"Proxying health check to: {service_url}")
        
        try:
            response = requests.get(f"{service_url}/health", timeout=20)
            response.raise_for_status()
            return JSONResponse(content=response.json())
        except Exception as e:
            logger.error(f"Health proxy error for {package_name}: {e}")
            raise HTTPException(status_code=503, detail=f"Health check failed: {str(e)}")
    
    @router.post(f"/{package_name}/mcp", tags=[package_name])
    def proxy_jsonrpc(request: Dict[str, Any] = Body(...), token: str = Depends(get_token)):
        """Main proxy endpoint with health check and auto-retry"""
        return _proxy_request_with_retry(
            package_name=package_name,
            endpoint=f"{package_name}/mcp",
            method="POST",
            request_body=request
        )
    
    @router.get(f"/{package_name}/mcp/tools/list", tags=[package_name])
    def list_tools(token: str = Depends(get_token)):
        """Proxy tools/list with health check"""
        return _proxy_request_with_retry(
            package_name=package_name,
            endpoint=f"{package_name}/mcp/tools/list",
            method="GET"
        )
    
    @router.post(f"/{package_name}/mcp/tools/call", tags=[package_name])
    def call_tool(request_body: Dict[str, Any] = Body(...), token: str = Depends(get_token)):
        """Proxy tools/call with health check"""
        return _proxy_request_with_retry(
            package_name=package_name,
            endpoint=f"{package_name}/mcp/tools/call",
            method="POST",
            request_body=request_body
        )
    
    return router