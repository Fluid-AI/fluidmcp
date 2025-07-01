import os
import json
import subprocess
import shutil
import uuid
import asyncio
from typing import AsyncGenerator, Dict, Any, Union
from pathlib import Path
from loguru import logger
import time
from fastapi import FastAPI, Request, APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn

# Import utilities
from .utils import (
    fix_npm_permissions, 
    create_clean_npm_environment, 
    initialize_mcp_server,
    active_sessions,
    persistent_tool_sessions
)

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
    """Launch MCP server and return package name and router"""
    dest_dir = Path(dest_dir)
    metadata_path = dest_dir / "metadata.json"

    try:
        if not metadata_path.exists():
            logger.info(f":warning: No metadata.json found at {metadata_path}")
            return None, None
        print(f":blue_book: Reading metadata.json from {metadata_path}")
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        pkg = list(metadata["mcpServers"].keys())[0]
        servers = metadata['mcpServers'][pkg]
        print(pkg, servers)
    except Exception as e:
        print(f":x: Error reading metadata.json: {e}")
        return None, None

    try:
        base_command = servers["command"]
        raw_args = servers["args"]
        
        # Handle npm/npx commands with permission fixes
        if base_command in ["npx", "npm"]:
            fix_npm_permissions()
            command_path = shutil.which(base_command)
            if command_path:
                base_command = command_path
            clean_npm_env = create_clean_npm_environment()
        else:
            clean_npm_env = {}
        
        args = [arg.replace("<path to mcp-servers>", str(dest_dir)) for arg in raw_args]
        stdio_command = [base_command] + args
        
        # Combine environments
        env_vars = servers.get("env", {})
        env = {**dict(os.environ), **env_vars, **clean_npm_env}
        
        print(f"🔍 Attempting to launch: {stdio_command}")
        print(f"🔍 Working directory: {dest_dir}")
        print(f"🔍 Environment vars: {list(env_vars.keys())}")
        
        # Try with clean environment first
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
        
        # Check if process started successfully
        time.sleep(2)
        
        if process.poll() is not None:
            stderr_output = process.stderr.read()
            print(f"❌ Process terminated. Exit code: {process.returncode}")
            print(f"❌ Error output: {stderr_output}")
            
            # Try fallback: use npx with --no-install
            if base_command.endswith("npx") and "-y" in args:
                print("🔄 Trying fallback with --no-install...")
                fallback_args = [arg.replace("-y", "--no-install") for arg in args]
                fallback_command = [base_command] + fallback_args
                
                process = subprocess.Popen(
                    fallback_command,
                    cwd=dest_dir,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=env,
                    text=True,
                    bufsize=1
                )
                
                time.sleep(1)
                if process.poll() is not None:
                    print("❌ Fallback also failed")
                    return None, None
        
        print(f"✅ Process started successfully with PID: {process.pid}")
        
        # Initialize MCP server
        if not initialize_mcp_server(process):
            print(f"Warning: Failed to initialize MCP server for {pkg}")
            if process.poll() is not None:
                stderr_output = process.stderr.read()
                print(f"Process error output: {stderr_output}")
        
        router = create_mcp_router(pkg, process)
        return pkg, router
        
    except FileNotFoundError as e:
        print(f":x: Command not found: {e}")
        return None, None
    except Exception as e:
        print(f":x: Error launching MCP server: {e}")
        return None, None

def create_mcp_router(package_name: str, process: subprocess.Popen) -> APIRouter:
    """Create FastAPI router with all MCP endpoints for a package"""
    router = APIRouter()

    @router.post(f"/{package_name}/mcp", tags=[package_name])
    async def proxy_jsonrpc(
        request: Dict[str, Any] = Body(...), 
        token: str = Depends(get_token)
    ):
        """Direct MCP JSON-RPC proxy endpoint"""
        try:
            msg = json.dumps(request)
            process.stdin.write(msg + "\n")
            process.stdin.flush()
            response_line = process.stdout.readline()
            return JSONResponse(content=json.loads(response_line))
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
    
    # ===== STANDARD SSE PATTERN IMPLEMENTATION =====
    
    @router.post(f"/{package_name}/sse/start", tags=[package_name])
    async def start_sse_session(token: str = Depends(get_token)):
        """Start a new empty SSE session"""
        try:
            session_id = str(uuid.uuid4())
            
            active_sessions[session_id] = {
                "messages": [],
                "processed_count": 0,
                "status": "ready",
                "created_at": time.time(),
                "package_name": package_name,
                "process": process,
                "context": {}
            }
            
            return JSONResponse(content={
                "session_id": session_id,
                "status": "ready",
                "message_url": f"/{package_name}/sse/message?session_id={session_id}",
                "stream_url": f"/{package_name}/sse/stream?session_id={session_id}"
            })
            
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})

    @router.post(f"/{package_name}/sse/message", tags=[package_name])
    async def add_message(
        request: Dict[str, Any] = Body(...),
        session_id: str = Query(...),
        token: str = Depends(get_token)
    ):
        """Add message to session queue"""
        if session_id not in active_sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = active_sessions[session_id]
        message_id = str(uuid.uuid4())
        message = {
            "id": message_id,
            "content": request,
            "timestamp": time.time(),
            "status": "queued"
        }
        
        session['messages'].append(message)
        session['status'] = "has_new_messages"
        
        return JSONResponse(content={
            "message_id": message_id,
            "status": "queued",
            "queue_position": len(session['messages']),
            "session_status": session['status']
        })
    
    @router.get(f"/{package_name}/sse/stream", tags=[package_name])
    async def stream_sse(
        session_id: str = Query(...),
        token: str = Depends(get_token)
    ):
        """Stream real-time responses as server processes message queue"""
        if session_id not in active_sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = active_sessions[session_id]
        
        async def event_generator() -> AsyncGenerator[str, None]:
            try:
                yield f"event: connected\ndata: {json.dumps({'session_id': session_id, 'status': 'connected'})}\n\n"
                
                while session_id in active_sessions:
                    session = active_sessions[session_id]
                    total_messages = len(session['messages'])
                    processed_count = session['processed_count']
                    
                    if total_messages > processed_count:
                        for i in range(processed_count, total_messages):
                            message = session['messages'][i]
                            
                            yield f"event: processing\ndata: {json.dumps({'message_id': message['id'], 'status': 'processing'})}\n\n"
                            
                            try:
                                mcp_request = message["content"]
                                msg = json.dumps(mcp_request)
                                process.stdin.write(msg + "\n")
                                process.stdin.flush()
                                
                                response_line = process.stdout.readline()
                                if response_line:
                                    response_line = response_line.strip()
                                    yield f"event: response\ndata: {response_line}\n\n"
                                    
                                    message['status'] = "completed"
                                    message["response"] = response_line
                                    
                                    try:
                                        response_data = json.loads(response_line)
                                        if "error" in response_data:
                                            yield f"event: error\ndata: {response_line}\n\n"
                                        elif "result" in response_data:
                                            yield f"event: result\ndata: {json.dumps(session['messages'])}\n\n"
                                    except json.JSONDecodeError:
                                        yield f"event: text\ndata: {json.dumps({'text': response_line})}\n\n"
                                
                            except Exception as e:
                                error_data = json.dumps({"message_id": message['id'], "error": str(e)})
                                yield f"event: error\ndata: {error_data}\n\n"
                                message['status'] = "error"
                            
                            session['processed_count'] += 1
                    
                    if processed_count >= total_messages and session.get("status") != "has_new_messages":
                        yield f"event: idle\ndata: {json.dumps({'status': 'waiting_for_messages'})}\n\n"
                    
                    session['status'] = "ready"
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                error_data = json.dumps({"error": str(e), "session_id": session_id})
                yield f"event: error\ndata: {error_data}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    
    # ===== MCP TOOLS ENDPOINTS =====
    
    @router.get(f"/{package_name}/mcp/tools/list", tags=[package_name])
    async def list_tools(token: str = Depends(get_token)):
        """List available tools from MCP server"""
        try:
            request_payload = {"id": 1, "jsonrpc": "2.0", "method": "tools/list"}
            msg = json.dumps(request_payload)
            process.stdin.write(msg + "\n")
            process.stdin.flush()
            response_line = process.stdout.readline()
            return JSONResponse(content=json.loads(response_line))
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
        
    @router.post(f"/{package_name}/mcp/tools/call", tags=[package_name])
    async def call_tool(
        request_body: Dict[str, Any] = Body(...), 
        token: str = Depends(get_token)
    ):
        """Call a specific tool"""
        try:
            if "name" not in request_body:
                return JSONResponse(status_code=400, content={"error": "Tool name is required"})
            
            request_payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": request_body
            }
            
            msg = json.dumps(request_payload)
            process.stdin.write(msg + "\n")
            process.stdin.flush()
            response_line = process.stdout.readline()
            return JSONResponse(content=json.loads(response_line))
            
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})
    
    # ===== PERSISTENT SESSION ENDPOINTS =====
    
    @router.post(f"/{package_name}/sse/tools/call", tags=[package_name])
    async def sse_tools_call(
        request: Dict[str, Any] = Body(...),
        timeout: int = Query(30),
        reset_session: bool = Query(False),
        token: str = Depends(get_token)
    ):
        """Convenient endpoint that maintains persistent session per package"""
        session_id = None
        is_new_session = False
        
        try:
            # Get or create persistent session
            if reset_session and package_name in persistent_tool_sessions:
                old_session_id = persistent_tool_sessions[package_name]
                if old_session_id in active_sessions:
                    del active_sessions[old_session_id]
                del persistent_tool_sessions[package_name]
            
            if package_name in persistent_tool_sessions:
                session_id = persistent_tool_sessions[package_name]
                if session_id not in active_sessions:
                    del persistent_tool_sessions[package_name]
                    session_id = None
            
            if session_id is None:
                session_id = str(uuid.uuid4())
                is_new_session = True
                
                active_sessions[session_id] = {
                    "messages": [],
                    "processed_count": 0,
                    "status": "ready",
                    "created_at": time.time(),
                    "package_name": package_name,
                    "process": process,
                    "context": {},
                    "persistent": True
                }
                
                persistent_tool_sessions[package_name] = session_id
            
            session = active_sessions[session_id]
            
            # Add message and process
            message_id = str(uuid.uuid4())
            message = {
                "id": message_id,
                "content": request,
                "timestamp": time.time(),
                "status": "queued"
            }
            
            session['messages'].append(message)
            session['status'] = "has_new_messages"
            session["last_used"] = time.time()
            
            # Wait for completion
            start_time = time.time()
            current_message_index = len(session['messages']) - 1
            
            while time.time() - start_time < timeout:
                session = active_sessions[session_id]
                
                if current_message_index < session['processed_count']:
                    processed_message = session['messages'][current_message_index]
                    
                    if processed_message['status'] == "completed":
                        return JSONResponse(content={
                            "message_id": message_id,
                            "session_id": session_id,
                            "is_new_session": is_new_session,
                            "total_messages": len(session['messages']),
                            "messages": session['messages']
                        })
                    elif processed_message['status'] == "error":
                        error_detail = processed_message.get("error", "Unknown MCP error")
                        raise HTTPException(status_code=500, detail=f"MCP processing error: {error_detail}")
                
                # Process pending messages
                total_messages = len(session['messages'])
                processed_count = session['processed_count']
                
                if total_messages > processed_count:
                    message_to_process = session['messages'][processed_count]
                    
                    try:
                        mcp_request = message_to_process["content"]
                        msg = json.dumps(mcp_request)
                        process.stdin.write(msg + "\n")
                        process.stdin.flush()
                        
                        response_line = process.stdout.readline()
                        if response_line:
                            response_line = response_line.strip()
                            message_to_process["status"] = "completed"
                            message_to_process["response"] = response_line
                            session['processed_count'] += 1
                            continue
                            
                    except Exception as e:
                        message_to_process["status"] = "error"
                        message_to_process["error"] = str(e)
                        session['processed_count'] += 1
                        continue
                
                await asyncio.sleep(0.1)
            
            raise HTTPException(status_code=408, detail=f"Request timeout after {timeout} seconds")
            
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    # ===== SESSION MANAGEMENT =====
    
    @router.get(f"/{package_name}/sse/status/{{session_id}}", tags=[package_name])
    async def get_session_status(session_id: str, token: str = Depends(get_token)):
        """Get session status"""
        if session_id not in active_sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = active_sessions[session_id]
        return JSONResponse(content={
            "session_id": session_id,
            "status": session['status'],
            "created_at": session["created_at"],
            "package_name": session["package_name"],
            "message_count": len(session.get("messages", [])),
            "processed_count": session.get("processed_count", 0)
        })
    
    @router.delete(f"/{package_name}/sse/{{session_id}}", tags=[package_name])
    async def cancel_session(session_id: str, token: str = Depends(get_token)):
        """Cancel session"""
        if session_id not in active_sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        del active_sessions[session_id]
        return JSONResponse(content={"session_id": session_id, "status": "cancelled"})
    
    @router.delete(f"/{package_name}/sse/tools/session", tags=[package_name])
    async def cleanup_persistent_session(token: str = Depends(get_token)):
        """Clean up persistent session for package"""
        if package_name in persistent_tool_sessions:
            session_id = persistent_tool_sessions[package_name]
            if session_id in active_sessions:
                del active_sessions[session_id]
            del persistent_tool_sessions[package_name]
            return JSONResponse(content={"package_name": package_name, "session_id": session_id, "status": "cleaned_up"})
        else:
            return JSONResponse(content={"package_name": package_name, "status": "no_persistent_session"})

    @router.get(f"/{package_name}/sse/tools/session/info", tags=[package_name])
    async def get_persistent_session_info(token: str = Depends(get_token)):
        """Get persistent session info"""
        if package_name in persistent_tool_sessions:
            session_id = persistent_tool_sessions[package_name]
            if session_id in active_sessions:
                session = active_sessions[session_id]
                return JSONResponse(content={
                    "package_name": package_name,
                    "session_id": session_id,
                    "status": "active",
                    "created_at": session["created_at"],
                    "last_used": session.get("last_used", session["created_at"]),
                    "total_messages": len(session['messages']),
                    "processed_count": session['processed_count']
                })
            else:
                del persistent_tool_sessions[package_name]
                return JSONResponse(content={"package_name": package_name, "status": "orphaned_cleaned_up"})
        else:
            return JSONResponse(content={"package_name": package_name, "status": "no_persistent_session"})
    
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
