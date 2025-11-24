import os
import json
import subprocess
import shutil
from typing import Union, Dict, Any
from pathlib import Path
from loguru import logger
import time
import sys
import threading
import json
import subprocess
from pathlib import Path
from typing import Dict
from fastapi import FastAPI, Request, APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn
import threading
import requests


_global_thread_manager = None

def set_global_thread_manager(manager):
    global _global_thread_manager
    _global_thread_manager = manager
security = HTTPBearer(auto_error=False)


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
    dest_dir = Path(dest_dir)
    metadata_path = dest_dir / "metadata.json"
    
    logger.info(f"🚀 RAILWAY DEBUG: Starting MCP server launch from {dest_dir}")
    
    try:
        if not metadata_path.exists():
            logger.error(f"❌ RAILWAY DEBUG: No metadata.json found at {metadata_path}")
            return None, None, None  # <-- Added third None for process
            
        logger.info(f"📖 RAILWAY DEBUG: Reading metadata.json from {metadata_path}")
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
            
        pkg = list(metadata["mcpServers"].keys())[0]
        servers = metadata['mcpServers'][pkg]
        logger.info(f"📦 RAILWAY DEBUG: Package: {pkg}, Server config: {servers}")
        
    except Exception as e:
        logger.error(f"❌ RAILWAY DEBUG: Error reading metadata.json: {e}")
        return None, None, None  # <-- Added third None for process
        
    try:
        base_command = servers["command"]
        raw_args = servers["args"]
        
        logger.info(f"🔧 RAILWAY DEBUG: Original command: {base_command}")
        logger.info(f"🔧 RAILWAY DEBUG: Original args: {raw_args}")
        
        if base_command == "npx" or base_command == "npm":
            npm_path = shutil.which("npm")
            npx_path = shutil.which("npx")
            logger.info(f"🔍 RAILWAY DEBUG: npm path: {npm_path}, npx path: {npx_path}")
            
            if npm_path and base_command == "npm":
                base_command = npm_path
            elif npx_path and base_command == "npx":
                base_command = npx_path
                
        args = [arg.replace("<path to mcp-servers>", str(dest_dir)) for arg in raw_args]
        stdio_command = [base_command] + args

        # Determine the appropriate working directory based on package type
        # Check if this is a GitHub cloned repo
        is_github_repo = "/github/" in str(dest_dir) or "\\github\\" in str(dest_dir)

        if is_github_repo:
            # GitHub repo detected - different logic needed
            if base_command in [npx_path, npm_path, "npx", "npm"] and "-y" in args:
                # npx -y means published package online - use parent to avoid package.json conflict
                working_dir = dest_dir.parent
                logger.info(f"📂 RAILWAY DEBUG: GitHub repo with npx -y detected - using parent directory: {working_dir}")
            else:
                # Source code execution (node, npm start, python, etc.) - needs repo files
                working_dir = dest_dir
                logger.info(f"📂 RAILWAY DEBUG: GitHub repo with source code - using repo directory: {working_dir}")
        else:
            # Registry package - always use package directory (no conflicts)
            working_dir = dest_dir
            logger.info(f"📂 RAILWAY DEBUG: Registry package - using package directory: {working_dir}")

        logger.info(f"🚀 RAILWAY DEBUG: Final command: {stdio_command}")
        logger.info(f"📂 RAILWAY DEBUG: Working directory: {working_dir}")

        env_vars = servers.get("env", {})
        env = {**dict(os.environ), **env_vars}

        # Log environment variables (safely)
        logger.info(f"🌍 RAILWAY DEBUG: Environment variables count: {len(env)}")
        for key in env_vars.keys():
            logger.info(f"🌍 RAILWAY DEBUG: Custom env var: {key} = {'***' if 'key' in key.lower() or 'password' in key.lower() or 'token' in key.lower() else env_vars[key]}")

        # Check if the command exists
        if not shutil.which(base_command):
            logger.error(f"❌ RAILWAY DEBUG: Command not found: {base_command}")
            return None, None, None  # <-- Added third None for process

        logger.info(f"✅ RAILWAY DEBUG: Command exists, starting process...")

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
        
        logger.info(f"🔄 RAILWAY DEBUG: Process started with PID: {process.pid}")
        
        # Give the process a moment to start
        time.sleep(2)
        
        # Check if process is still alive
        if process.poll() is not None:
            logger.error(f"❌ RAILWAY DEBUG: Process died immediately with return code: {process.returncode}")
            # Try to read stderr for error details
            try:
                stderr_output = process.stderr.read()
                if stderr_output:
                    logger.error(f"❌ RAILWAY DEBUG: Process stderr: {stderr_output}")
            except:
                pass
            return None, None, None  # <-- Added third None for process
        else:
            logger.info(f"✅ RAILWAY DEBUG: Process is running successfully")
        
        # Initialize MCP server with enhanced logging
        logger.info(f"🔧 RAILWAY DEBUG: Initializing MCP server...")
        if not initialize_mcp_server_with_logging(process, pkg):
            logger.error(f"❌ RAILWAY DEBUG: Failed to initialize MCP server for {pkg}")
            return None, None, None  # <-- Added third None for process
        else:
            logger.info(f"✅ RAILWAY DEBUG: MCP server initialized successfully for {pkg}")
               
        router = create_mcp_router(pkg, process)
        logger.info(f"🌐 RAILWAY DEBUG: Router created successfully for {pkg}")
        return pkg, router, process  # <-- CHANGED: Now returning process as third value
        
    except FileNotFoundError as e:
        logger.error(f"❌ RAILWAY DEBUG: Command not found: {e}")
        return None, None, None  # <-- Added third None for process
    except Exception as e:
        logger.error(f"❌ RAILWAY DEBUG: Error launching MCP server: {e}")
        logger.error(f"❌ RAILWAY DEBUG: Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ RAILWAY DEBUG: Traceback: {traceback.format_exc()}")
        return None, None, None  # <-- Added third None for process


def initialize_mcp_server_with_logging(process: subprocess.Popen, pkg_name: str, timeout=300) -> bool:
    """Initialize and verify MCP server is responding with detailed logging"""
    logger.info(f"🔧 RAILWAY DEBUG: Starting MCP server initialization for {pkg_name}")
    
    try:
        # Send initialization request - CORRECTED FORMAT
        init_request = {
            "jsonrpc": "2.0",
            "id": 0,  # Use ID 0 like the working version
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"roots": {"listChanged": True}, "sampling": {}},  # Full capabilities
                "clientInfo": {"name": "fluidmcp-client", "version": "1.0.0"}  # Client info
            }
        }
        
        logger.info(f"📤 RAILWAY DEBUG: Sending init request: {json.dumps(init_request)}")
        
        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()
        
        logger.info(f"📤 RAILWAY DEBUG: Init request sent, waiting for response...")
        
        # Wait for response with timeout
        start_time = time.time()
        while time.time() - start_time < timeout:
            # Check if process died
            if process.poll() is not None:
                logger.error(f"❌ RAILWAY DEBUG: MCP server process died during initialization (return code: {process.returncode})")
                return False
            
            # Check for stderr output (errors)
            try:
                import select
                if hasattr(select, 'select'):  # Unix-like systems
                    ready, _, _ = select.select([process.stderr], [], [], 0.1)
                    if ready:
                        stderr_line = process.stderr.readline()
                        if stderr_line:
                            logger.error(f"🚨 RAILWAY DEBUG: MCP server stderr: {stderr_line.strip()}")
            except:
                pass
            
            # Check for stdout response
            try:
                if hasattr(select, 'select'):
                    ready, _, _ = select.select([process.stdout], [], [], 0.1)
                    if ready:
                        response_line = process.stdout.readline()
                        if response_line:
                            logger.info(f"📥 RAILWAY DEBUG: Got response: {response_line.strip()}")
                            try:
                                response = json.loads(response_line)
                                # Check for the correct response - CORRECTED
                                if response.get("id") == 0 and "result" in response:
                                    logger.info(f"✅ RAILWAY DEBUG: Got valid initialization response")
                                    
                                    # Send initialized notification - THIS WAS MISSING!
                                    notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
                                    logger.info(f"📤 RAILWAY DEBUG: Sending initialized notification: {json.dumps(notif)}")
                                    process.stdin.write(json.dumps(notif) + "\n")
                                    process.stdin.flush()
                                    
                                    logger.info(f"✅ RAILWAY DEBUG: MCP server initialized successfully for {pkg_name}")
                                    return True
                                else:
                                    logger.warning(f"⚠️ RAILWAY DEBUG: Got response but wrong format: {response}")
                            except json.JSONDecodeError as e:
                                logger.error(f"❌ RAILWAY DEBUG: Invalid JSON response: {e}, Raw: {response_line}")
                else:
                    # Fallback for systems without select
                    time.sleep(0.1)
                        
            except Exception as e:
                logger.error(f"❌ RAILWAY DEBUG: Error reading stdout: {e}")
                
            time.sleep(0.1)
            
        logger.error(f"❌ RAILWAY DEBUG: MCP server initialization timed out after {timeout}s for {pkg_name}")
        return False
        
    except Exception as e:
        logger.error(f"❌ RAILWAY DEBUG: Error initializing MCP server for {pkg_name}: {e}")
        import traceback
        logger.error(f"❌ RAILWAY DEBUG: Initialization traceback: {traceback.format_exc()}")
        return False


def create_fastapi_jsonrpc_proxy_with_logging(package_name: str, process: subprocess.Popen) -> FastAPI:
    app = FastAPI()
    
    @app.post(f"/{package_name}/mcp")
    async def proxy_jsonrpc(request: Request):
        logger.info(f"🌐 RAILWAY DEBUG: Received request for {package_name}")
        
        try:
            # Check if process is still alive
            if process.poll() is not None:
                logger.error(f"❌ RAILWAY DEBUG: MCP server process is dead (return code: {process.returncode})")
                return JSONResponse(status_code=500, content={"error": f"MCP server process has died"})
            
            jsonrpc_request = await request.body()
            jsonrpc_str = jsonrpc_request.decode() if isinstance(jsonrpc_request, bytes) else jsonrpc_request
            
            logger.info(f"📤 RAILWAY DEBUG: Sending to {package_name}: {jsonrpc_str[:200]}...")
            
            # Send to MCP server via stdin
            process.stdin.write(jsonrpc_str + "\n")
            process.stdin.flush()
            
            logger.info(f"📤 RAILWAY DEBUG: Request sent to {package_name}, waiting for response...")
            
            # Read from MCP server stdout with timeout
            import time
            start_time = time.time()
            timeout = 180
            
            while time.time() - start_time < timeout:
                if process.poll() is not None:
                    logger.error(f"❌ RAILWAY DEBUG: Process died while waiting for response")
                    return JSONResponse(status_code=500, content={"error": "MCP server process died"})
                
                try:
                    response_line = process.stdout.readline()
                    if response_line:
                        logger.info(f"📥 RAILWAY DEBUG: Got response from {package_name}: {response_line[:200]}...")
                        return JSONResponse(content=json.loads(response_line))
                except json.JSONDecodeError as e:
                    logger.error(f"❌ RAILWAY DEBUG: Invalid JSON response: {e}")
                    return JSONResponse(status_code=500, content={"error": "Invalid JSON response from MCP server"})
                
                time.sleep(0.01)  # Small delay
            
            logger.error(f"❌ RAILWAY DEBUG: Timeout waiting for response from {package_name}")
            return JSONResponse(status_code=500, content={"error": "Timeout waiting for MCP server response"})
            
        except Exception as e:
            logger.error(f"❌ RAILWAY DEBUG: Proxy error for {package_name}: {e}")
            import traceback
            logger.error(f"❌ RAILWAY DEBUG: Proxy traceback: {traceback.format_exc()}")
            return JSONResponse(status_code=500, content={"error": str(e)})
    
    return app


def start_fastapi_in_thread(app: FastAPI, port: int):
    def run():
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    thread = threading.Thread(target=run, daemon=True)
    thread.start()


def initialize_mcp_server(process: subprocess.Popen) -> bool:
    """Initialize MCP server with proper handshake"""
    try:
        import time
        
        # Send initialize request
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
        
        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()
        
        # Wait for response
        start_time = time.time()
        while time.time() - start_time < 10:
            if process.poll() is not None:
                return False
            response_line = process.stdout.readline().strip()
            if response_line:
                response = json.loads(response_line)
                if response.get("id") == 0 and "result" in response:
                    # Send initialized notification
                    notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
                    process.stdin.write(json.dumps(notif) + "\n")
                    process.stdin.flush()
                    return True
            time.sleep(0.1)
        return False
    except Exception as e:
        print(f"Initialization error: {e}")
        return False
    
import asyncio

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

            response_line = await asyncio.wait_for(
            asyncio.to_thread(process.stdout.readline), 
            timeout=300
        )
            return JSONResponse(content=json.loads(response_line))
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
        
        
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
    Simple function to check if the MCP service is healthy
    Returns True if healthy, raises HTTPException if not
    """
    global _global_thread_manager
    
    if _global_thread_manager is None:
        logger.error(f"❌ RAILWAY DEBUG: No global thread manager available")
        raise HTTPException(status_code=503, detail="Thread manager not initialized")
    
    try:
        # Hit the existing health endpoint
        response = requests.get(f"{service_url}/health", timeout=20)
        
        if response.status_code != 200:
            logger.error(f"❌ RAILWAY DEBUG: Health check failed for {package_name} - HTTP {response.status_code}")

            # Get dest_dir from thread manager
            old_thread = _global_thread_manager.threads.get(package_name)
            if old_thread:
                dest_dir = old_thread.dest_dir
                logger.info("Entering restart_mcp_thread")
                success = _global_thread_manager.restart_mcp_thread(package_name, dest_dir)
                
                if success:
                    logger.info(f"✅ RAILWAY DEBUG: Successfully restarted {package_name}")
                    return True
                else:
                    logger.info("Success failed")
                    logger.error(f"❌ RAILWAY DEBUG: Restart failed for {package_name}")
            
            raise HTTPException(status_code=503, detail=f"Service restart failed for {package_name}")
        
        logger.info(f"✅ RAILWAY DEBUG: Health check passed for {package_name}, Service URL : {service_url}")
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ RAILWAY DEBUG: Cannot reach {package_name} health endpoint: {str(e)}")
        raise HTTPException(
            status_code=503, 
            detail=f"Cannot reach {package_name} service"
        )

def create_proxy_mcp_router(package_name: str, service_url: str, secure_mode: bool = False):
    """
    Simple proxy router that checks health before each request
    """
    router = APIRouter()

    @router.get(f"/{package_name}/health", tags=[package_name])
    def proxy_health_check(token: str = Depends(get_token)):
        """Proxy the health check to the mini-FastAPI"""

        # 🎯 KEY FIX: Get service URL dynamically at request time
        service_url = _global_thread_manager.service_registry.get(package_name)
        logger.info(f"🔗 RAILWAY DEBUG: Using service URL: {service_url}")
        
        try:
            response = requests.get(f"{service_url}/health", timeout=180)
            response.raise_for_status()
            return JSONResponse(content=response.json())
        except Exception as e:
            logger.error(f"❌ Health proxy error for {package_name}: {e}")
            raise HTTPException(status_code=503, detail=f"Health check failed: {str(e)}")

    @router.post(f"/{package_name}/mcp", tags=[package_name])
    def proxy_jsonrpc(request: Dict[str, Any] = Body(...), token: str = Depends(get_token)):
        logger.info(f"🌐 RAILWAY DEBUG: Endpoint hit - /{package_name}/mcp")
        
        # 🎯 KEY FIX: Get service URL dynamically at request time
        service_url = _global_thread_manager.service_registry.get(package_name)
        logger.info(f"🔗 RAILWAY DEBUG: Using service URL: {service_url}")
        
        check_service_health(package_name, service_url)
        
        try:
            response = requests.post(f"{service_url}/{package_name}/mcp", json=request, timeout=180)
            response.raise_for_status()
            return JSONResponse(content=response.json())
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
            # Use existing restart logic from check_service_health
            logger.error(f"❌ RAILWAY DEBUG: Service error for {package_name}: {str(e)}")
            
            # Restart the thread (reuse existing logic)
            old_thread = _global_thread_manager.threads.get(package_name)
            if old_thread:
                success = _global_thread_manager.restart_mcp_thread(package_name, old_thread.dest_dir)
                if success:
                    # Retry once with new service URL
                    new_service_url = _global_thread_manager.service_registry.get(package_name)
                    response = requests.post(f"{new_service_url}/{package_name}/mcp", json=request, timeout=180)
                    return JSONResponse(content=response.json())
            
                raise HTTPException(status_code=503, detail=f"Service restart failed for {package_name}")
        
    @router.get(f"/{package_name}/mcp/tools/list", tags=[package_name])
    def list_tools(token: str = Depends(get_token)):
        logger.info(f"🔧 RAILWAY DEBUG: Endpoint hit - /{package_name}/mcp/list/tools")

        # 🎯 KEY FIX: Get service URL dynamically at request time
        service_url = _global_thread_manager.service_registry.get(package_name)
        logger.info(f"🔗 RAILWAY DEBUG: Using service URL: {service_url}")
        
        # Check health first
        check_service_health(package_name, service_url)
        
        try:
            logger.info(f"📤 RAILWAY DEBUG: Forwarding request to: {service_url}/{package_name}/mcp/tools/list")
            response = requests.get(f"{service_url}/{package_name}/mcp/tools/list", timeout=180)
            response.raise_for_status()
            return JSONResponse(content=response.json())
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
            # Use existing restart logic from check_service_health
            logger.error(f"❌ RAILWAY DEBUG: Service error for {package_name}: {str(e)}")
        
            # Restart the thread (reuse existing logic)
            old_thread = _global_thread_manager.threads.get(package_name)
            if old_thread:
                success = _global_thread_manager.restart_mcp_thread(package_name, old_thread.dest_dir)
                if success:
                    # Retry once with new service URL
                    new_service_url = _global_thread_manager.service_registry.get(package_name)
                    response = requests.post(f"{new_service_url}/{package_name}/mcp", timeout=180)
                    return JSONResponse(content=response.json())
            
            raise HTTPException(status_code=503, detail=f"Service restart failed for {package_name}")
    
    @router.post(f"/{package_name}/mcp/tools/call", tags=[package_name])
    def call_tool(
        request_body: Dict[str, Any] = Body(...),
        token: str = Depends(get_token)
    ):
        logger.info(f"🔧 RAILWAY DEBUG: Endpoint hit - /{package_name}/mcp/tools/call")

        # 🎯 KEY FIX: Get service URL dynamically at request time
        service_url = _global_thread_manager.service_registry.get(package_name)
        logger.info(f"🔗 RAILWAY DEBUG: Using service URL: {service_url}")

        # Check health first
        check_service_health(package_name, service_url)
        
        try:
            logger.info(f"📤 RAILWAY DEBUG: Forwarding request to: {service_url}/{package_name}/mcp/tools/list")
            #response = requests.post(f"{service_url}/{package_name}/mcp/tools/list", timeout=30)

            response = requests.post(
                f"{service_url}/{package_name}/mcp/tools/call", 
                json=request_body, 
                timeout=180
            )
            response.raise_for_status()
            return JSONResponse(content=response.json())
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError, requests.exceptions.HTTPError) as e:
            # Use existing restart logic from check_service_health
            logger.error(f"❌ RAILWAY DEBUG: Service error for {package_name}: {str(e)}")
          
            # Restart the thread (reuse existing logic)
            old_thread = _global_thread_manager.threads.get(package_name)
            if old_thread:
                success = _global_thread_manager.restart_mcp_thread(package_name, old_thread.dest_dir)
                if success:
                    # Retry once with new service URL
                    new_service_url = _global_thread_manager.service_registry.get(package_name)
                    response = requests.post(f"{new_service_url}/{package_name}/mcp", json=request, timeout=180)
                    return JSONResponse(content=response.json())
            
            raise HTTPException(status_code=503, detail=f"Service restart failed for {package_name}")
                                    
    return router

if __name__ == '__main__':
    app = FastAPI()
    install_paths = [
        "/workspaces/fluid-ai-gpt-mcp/fluidmcp/.fmcp-packages/Perplexity/perplexity-ask/0.1.0",
        "/workspaces/fluid-ai-gpt-mcp/fluidmcp/.fmcp-packages/Airbnb/airbnb/0.1.0"
    ]
    for install_path in install_paths:
        print(f"Launching MCP server for {install_path}")
        package_name, router = launch_mcp_using_fastapi_proxy(install_path)
        if package_name is not None and router is not None:
            app.include_router(router)
        else:
            print(f"Skipping {install_path} due to missing metadata or launch error.")
    uvicorn.run(app, host="0.0.0.0", port=8099)
