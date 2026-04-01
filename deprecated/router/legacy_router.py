"""
DEPRECATED: Static per-server router implementation.

These functions were used by `fluidmcp run` and `fluidmcp github` before the
router was unified with `fluidmcp serve`.

The new approach uses create_dynamic_router(server_manager) from
fluidmcp.cli.services.package_launcher, which provides a single APIRouter
with {server_name} path-parameter dispatch backed by ServerManager.processes.

Retained here for reference only. Do not import or use in new code.
"""
import json
import subprocess
import threading
from typing import Dict, Any, Iterator

from fastapi import FastAPI, Request, APIRouter, Body, Depends
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn

from fluidmcp.cli.services.package_launcher import get_token
from fluidmcp.cli.services.metrics import MetricsCollector, RequestTimer


def create_fastapi_jsonrpc_proxy(package_name: str, process: subprocess.Popen) -> FastAPI:
    """
    DEPRECATED: Creates a complete FastAPI app for a single MCP server.
    Use create_dynamic_router(server_manager) instead.
    """
    app = FastAPI()

    @app.post(f"/{package_name}/mcp")
    async def proxy_jsonrpc(request: Request):
        try:
            jsonrpc_request = await request.body()
            jsonrpc_str = jsonrpc_request.decode() if isinstance(jsonrpc_request, bytes) else jsonrpc_request
            process.stdin.write(jsonrpc_str + "\n")
            process.stdin.flush()
            response_line = process.stdout.readline()
            return JSONResponse(content=json.loads(response_line))
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": str(e)})

    return app


def start_fastapi_in_thread(app: FastAPI, port: int):
    """
    DEPRECATED: Starts a FastAPI app in a daemon thread.
    Use asyncio-based server startup (uvicorn.run / asyncio.run) instead.
    """
    def run():
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()


def create_mcp_router(package_name: str, process: subprocess.Popen, process_lock: threading.Lock = None) -> APIRouter:
    """
    DEPRECATED: Creates a static APIRouter for a single MCP server process.
    Use create_dynamic_router(server_manager) instead.

    This approach mounts one router per server at app startup. The new dynamic
    router dispatches at runtime via ServerManager.processes, matching the
    behavior of `fluidmcp serve`.
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

        with RequestTimer(collector, method):
            try:
                all_headers = dict(http_request.headers)

                if request.get("method") == "tools/call" and all_headers:
                    params = request.get("params", {})
                    if "arguments" not in params:
                        params["arguments"] = {}
                    params["arguments"]["headers"] = all_headers
                    request["params"] = params

                with process_lock:
                    msg = json.dumps(request)
                    process.stdin.write(msg + "\n")
                    process.stdin.flush()
                    response_line = process.stdout.readline()

                return JSONResponse(content=json.loads(response_line))
            except Exception as e:
                return JSONResponse(status_code=500, content={"error": str(e)})

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
        all_headers = dict(http_request.headers)

        if request.get("method") == "tools/call" and all_headers:
            params = request.get("params", {})
            if "arguments" not in params:
                params["arguments"] = {}
            params["arguments"]["headers"] = all_headers
            request["params"] = params

        collector = MetricsCollector(package_name)

        async def event_generator() -> Iterator[str]:
            completion_status = "success"
            try:
                collector.increment_active_streams()

                with process_lock:
                    msg = json.dumps(request)
                    process.stdin.write(msg + "\n")
                    process.stdin.flush()

                    while True:
                        response_line = process.stdout.readline()
                        if not response_line:
                            break

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
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                collector.record_streaming_request(completion_status)
                collector.decrement_active_streams()

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @router.get(f"/{package_name}/mcp/tools/list", tags=[package_name])
    async def list_tools(token: str = Depends(get_token)):
        collector = MetricsCollector(package_name)

        with RequestTimer(collector, "tools/list"):
            try:
                request_payload = {"id": 1, "jsonrpc": "2.0", "method": "tools/list"}

                with process_lock:
                    msg = json.dumps(request_payload)
                    process.stdin.write(msg + "\n")
                    process.stdin.flush()
                    response_line = process.stdout.readline()

                return JSONResponse(content=json.loads(response_line))
            except Exception as e:
                return JSONResponse(status_code=500, content={"error": str(e)})

    @router.post(f"/{package_name}/mcp/tools/call", tags=[package_name])
    async def call_tool(
        http_request: Request,
        request_body: Dict[str, Any] = Body(
            ...,
            alias="params",
            example={"name": ""}
        ), token: str = Depends(get_token)
    ):
        params = request_body
        collector = MetricsCollector(package_name)
        tool_name = params.get("name", "unknown")

        with RequestTimer(collector, f"tools/call:{tool_name}"):
            try:
                if "name" not in params:
                    return JSONResponse(status_code=400, content={"error": "Tool name is required"})

                all_headers = dict(http_request.headers)
                if all_headers:
                    if "arguments" not in params:
                        params["arguments"] = {}
                    params["arguments"]["headers"] = all_headers

                request_payload = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": params
                }

                with process_lock:
                    msg = json.dumps(request_payload)
                    process.stdin.write(msg + "\n")
                    process.stdin.flush()
                    response_line = process.stdout.readline()

                return JSONResponse(content=json.loads(response_line))

            except json.JSONDecodeError:
                return JSONResponse(status_code=400, content={"error": "Invalid JSON in request body"})
            except Exception as e:
                return JSONResponse(status_code=500, content={"error": str(e)})

    return router
