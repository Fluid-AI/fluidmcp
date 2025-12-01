import os
import json
import subprocess
import shutil
import secrets
from typing import Union, Dict, Any, Iterator, Optional
from pathlib import Path
from loguru import logger
import time
from fastapi import FastAPI, Request, APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn
import threading

from fluidai_mcp.services.oauth2_pkce import OAuth2TokenManager, verify_oauth_token
from fluidai_mcp.services.oauth_service import (
    generate_pkce_pair,
    build_authorization_url,
    exchange_code_for_token,
    get_env_var
)

# Global in-memory storage for pending OAuth states
# Format: {state: {"verifier": str, "package_name": str, "auth_config": Dict}}
pending_auth_states: Dict[str, Dict[str, Any]] = {}

security = HTTPBearer(auto_error=False)


def get_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Validate bearer token if secure mode is enabled.
    Supports both simple bearer tokens and OAuth2 tokens.
    """
    secure_mode = os.environ.get("FMCP_SECURE_MODE") == "true"
    oauth_mode = os.environ.get("FMCP_OAUTH_MODE") == "true"

    # If neither mode is enabled, allow all requests
    if not secure_mode and not oauth_mode:
        return None

    # Check for credentials
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid or missing authorization token")

    token = credentials.credentials

    # OAuth2 mode - validate OAuth token
    if oauth_mode:
        if verify_oauth_token(token):
            return token
        raise HTTPException(status_code=401, detail="Invalid OAuth2 token")

    # Simple bearer token mode
    if secure_mode:
        bearer_token = os.environ.get("FMCP_BEARER_TOKEN")
        if token == bearer_token:
            return token
        raise HTTPException(status_code=401, detail="Invalid bearer token")

    return None


def launch_mcp_using_fastapi_proxy(dest_dir: Union[str, Path]):
    """
    Launch an MCP server and create a FastAPI router for it.

    Args:
        dest_dir: Path to the package directory containing metadata.json

    Returns:
        Tuple of (package_name, router, server_config) or (None, None, None) on error
    """
    dest_dir = Path(dest_dir)
    metadata_path = dest_dir / "metadata.json"

    try:
        if not metadata_path.exists():
            logger.info(f"No metadata.json found at {metadata_path}")
            return None, None, None

        logger.info(f"Reading metadata.json from {metadata_path}")
        with open(metadata_path, "r") as f:
            metadata = json.load(f)

        pkg = list(metadata["mcpServers"].keys())[0]
        server_config = metadata['mcpServers'][pkg]
        logger.info(f"Package: {pkg}, Config: {server_config}")

    except Exception as e:
        logger.error(f"Error reading metadata.json: {e}")
        return None, None, None

    try:
        base_command = server_config["command"]
        raw_args = server_config["args"]

        if base_command == "npx" or base_command == "npm":
            npm_path = shutil.which("npm")
            npx_path = shutil.which("npx")
            if npm_path and base_command == "npm":
                base_command = npm_path
            elif npx_path and base_command == "npx":
                base_command = npx_path

        args = [arg.replace("<path to mcp-servers>", str(dest_dir)) for arg in raw_args]
        stdio_command = [base_command] + args

        env_vars = server_config.get("env", {})
        env = {**dict(os.environ), **env_vars}

        process = subprocess.Popen(
            stdio_command,
            cwd=dest_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1
        )

        # Initialize MCP server
        if not initialize_mcp_server(process):
            logger.warning(f"Failed to initialize MCP server for {pkg}")

        # Pass server_config to create_mcp_router so it can check for auth
        router = create_mcp_router(pkg, process, server_config)
        return pkg, router, server_config

    except FileNotFoundError as e:
        logger.error(f"Command not found: {e}")
        return None, None, None
    except Exception as e:
        logger.error(f"Error launching MCP server: {e}")
        return None, None, None


def initialize_mcp_server(process: subprocess.Popen) -> bool:
    """Initialize MCP server with proper handshake"""
    try:
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
        logger.error(f"Initialization error: {e}")
        return False


def create_mcp_router(
    package_name: str,
    process: subprocess.Popen,
    server_config: Optional[Dict] = None
) -> APIRouter:
    """
    Create FastAPI router for MCP package with optional OAuth routes.

    Args:
        package_name: Name of the MCP package
        process: Subprocess running the MCP server
        server_config: Server configuration from metadata.json (optional)

    Returns:
        APIRouter with MCP endpoints and OAuth endpoints if configured
    """
    router = APIRouter()

    # Check if auth is configured in metadata
    if server_config and "auth" in server_config:
        auth_config = server_config["auth"]
        logger.info(f"Package {package_name} has OAuth configuration, adding auth endpoints")

        @router.get(f"/{package_name}/auth/login", tags=[package_name, "auth"])
        async def auth_login():
            """
            Initiate OAuth 2.0 login flow with PKCE.

            Returns:
                Redirect to OAuth provider's authorization page
            """
            try:
                # Generate PKCE pair
                verifier, challenge = generate_pkce_pair()

                # Generate random state for CSRF protection
                state = secrets.token_urlsafe(16)

                # Store verifier and config for callback
                pending_auth_states[state] = {
                    "verifier": verifier,
                    "package_name": package_name,
                    "auth_config": auth_config
                }

                # Build redirect URI
                redirect_uri = f"http://localhost:8099/{package_name}/auth/callback"

                # Build authorization URL
                auth_url = build_authorization_url(
                    auth_config=auth_config,
                    redirect_uri=redirect_uri,
                    state=state,
                    code_challenge=challenge
                )

                logger.info(f"Redirecting to OAuth provider for {package_name}")
                return RedirectResponse(url=auth_url)

            except Exception as e:
                logger.error(f"Error initiating auth flow: {e}")
                return JSONResponse(
                    status_code=500,
                    content={"error": f"Failed to initiate authentication: {str(e)}"}
                )

        @router.get(f"/{package_name}/auth/callback", tags=[package_name, "auth"])
        async def auth_callback(code: str, state: str):
            """
            Handle OAuth callback and exchange code for token.

            Args:
                code: Authorization code from OAuth provider
                state: State parameter for CSRF protection

            Returns:
                JSON response with access token and metadata
            """
            try:
                # Retrieve stored verifier and config
                auth_state = pending_auth_states.pop(state, None)
                if not auth_state:
                    logger.error(f"Invalid or expired state: {state}")
                    return JSONResponse(
                        status_code=400,
                        content={"error": "Invalid or expired state parameter"}
                    )

                verifier = auth_state["verifier"]
                stored_auth_config = auth_state["auth_config"]

                # Build redirect URI (must match the one used in login)
                redirect_uri = f"http://localhost:8099/{package_name}/auth/callback"

                # Exchange code for token
                token_data = exchange_code_for_token(
                    code=code,
                    verifier=verifier,
                    redirect_uri=redirect_uri,
                    auth_config=stored_auth_config
                )

                logger.info(f"Successfully obtained access token for {package_name}")

                # Return token to client
                return JSONResponse(content={
                    "success": True,
                    "package": package_name,
                    "token_data": token_data,
                    "message": "Authentication successful! Use the access_token in Authorization header."
                })

            except Exception as e:
                logger.error(f"Error in OAuth callback: {e}")
                return JSONResponse(
                    status_code=500,
                    content={"error": f"Failed to exchange code for token: {str(e)}"}
                )

    @router.post(f"/{package_name}/mcp", tags=[package_name])
    async def proxy_jsonrpc(
        request_obj: Request,
        json_body: Dict[str, Any] = Body(
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
        """
        Proxy JSON-RPC requests to MCP server.

        Supports Authorization header for package-specific OAuth tokens.
        """
        try:
            # Check for Authorization header
            auth_header = request_obj.headers.get("authorization")
            if auth_header:
                # Extract token from "Bearer <token>"
                if auth_header.startswith("Bearer "):
                    bearer_token = auth_header[7:]
                    logger.info(f"Received authenticated request for {package_name} with token")

                    # If package has auth config with env_var_name, we could inject it here
                    if server_config and "auth" in server_config:
                        env_var_name = server_config["auth"].get("env_var_name")
                        if env_var_name:
                            logger.info(f"Token should be set in {env_var_name} environment variable")
                            # Note: For subprocess, env is set at launch time
                            # For real implementation, might need to restart process with token
                else:
                    logger.warning(f"Invalid Authorization header format")

            # Convert dict to JSON string
            msg = json.dumps(json_body)
            process.stdin.write(msg + "\n")
            process.stdin.flush()

            # Read response
            response_line = process.stdout.readline()
            return JSONResponse(content=json.loads(response_line))

        except Exception as e:
            logger.error(f"Error proxying request: {e}")
            return JSONResponse(status_code=500, content={"error": str(e)})

    # SSE endpoint
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
        """Server-Sent Events streaming endpoint for long-running operations."""
        async def event_generator() -> Iterator[str]:
            try:
                msg = json.dumps(request)
                process.stdin.write(msg + "\n")
                process.stdin.flush()

                while True:
                    response_line = process.stdout.readline()
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

            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )

    @router.get(f"/{package_name}/mcp/tools/list", tags=[package_name])
    async def list_tools(token: str = Depends(get_token)):
        """List all available tools from the MCP server."""
        try:
            request_payload = {
                "id": 1,
                "jsonrpc": "2.0",
                "method": "tools/list"
            }

            msg = json.dumps(request_payload)
            process.stdin.write(msg + "\n")
            process.stdin.flush()

            response_line = process.stdout.readline()
            response_data = json.loads(response_line)

            return JSONResponse(content=response_data)

        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})

    @router.post(f"/{package_name}/mcp/tools/call", tags=[package_name])
    async def call_tool(
        request_body: Dict[str, Any] = Body(
            ...,
            alias="params",
            example={"name": ""}
        ),
        token: str = Depends(get_token)
    ):
        """Call a specific tool on the MCP server."""
        params = request_body

        try:
            if "name" not in params:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Tool name is required"}
                )

            request_payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": params
            }

            msg = json.dumps(request_payload)
            process.stdin.write(msg + "\n")
            process.stdin.flush()

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


if __name__ == '__main__':
    app = FastAPI()
    install_paths = [
        "/workspaces/fluid-ai-gpt-mcp/fluidmcp/.fmcp-packages/Perplexity/perplexity-ask/0.1.0",
        "/workspaces/fluid-ai-gpt-mcp/fluidmcp/.fmcp-packages/Airbnb/airbnb/0.1.0"
    ]
    for install_path in install_paths:
        print(f"Launching MCP server for {install_path}")
        package_name, router, _ = launch_mcp_using_fastapi_proxy(install_path)
        if package_name is not None and router is not None:
            app.include_router(router)
        else:
            print(f"Skipping {install_path} due to missing metadata or launch error.")
    uvicorn.run(app, host="0.0.0.0", port=8099)
