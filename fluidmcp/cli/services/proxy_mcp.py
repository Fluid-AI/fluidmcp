"""
Proxy MCP servers: an MCP tool that forwards its arguments to an HTTP endpoint.

A proxy MCP has no subprocess and no tool code. FluidMCP answers the MCP
protocol itself: tools/list returns the tool declared in the config, and
tools/call sends the tool arguments to the configured endpoint and returns the
upstream response as the tool result.

Config (one entry under mcpServers, or the body of POST /api/servers):

    {
      "type": "proxy",
      "endpoint": "https://api.openai.com/v1/chat/completions",
      "method": "POST",                      # optional, default POST
      "headers": {"Authorization": "Bearer ${OPENAI_API_KEY}"},
      "timeout": 50,                         # optional, seconds
      "response_path": "choices.0.message.content",   # optional
      "tool": {"name": "...", "description": "...", "inputSchema": {...}}
    }

Upstream failures are returned as tool results with isError=true rather than
as HTTP or JSON-RPC errors, so MCP clients that retry on transport errors
(FluidGPT retries up to 3 times) do not repeat a failed upstream call.
"""
import json
import re
import time
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlparse

import httpx
from loguru import logger

PROXY_TYPE = "proxy"

ALLOWED_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
# Methods whose tool arguments are sent as query parameters instead of a JSON body.
QUERY_METHODS = ("GET", "DELETE")

# Kept under FluidGPT's default 60s MCP_REQUEST_TIMEOUT so the client receives
# a clean tool error instead of hitting its own timeout and retrying.
DEFAULT_TIMEOUT_SECONDS = 50.0

# Same pattern OpenAI-style function calling accepts for tool names.
TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
VARIABLE_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

# Upstream error bodies are included in the tool result so the caller can see
# why the call failed; cap them so a large HTML error page doesn't flood it.
MAX_ERROR_BODY_CHARS = 2000


def is_proxy_config(config: Mapping[str, Any]) -> bool:
    return isinstance(config, Mapping) and config.get("type") == PROXY_TYPE


def validate_proxy_config(config: Mapping[str, Any]) -> List[str]:
    """Return a list of problems with a proxy server config (empty if valid)."""
    errors = []

    endpoint = config.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint.strip():
        errors.append("Missing required field: endpoint")
    else:
        parsed = urlparse(endpoint)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            errors.append("Field 'endpoint' must be an http:// or https:// URL")

    method = config.get("method", "POST")
    if not isinstance(method, str) or method.upper() not in ALLOWED_METHODS:
        errors.append(f"Field 'method' must be one of {', '.join(ALLOWED_METHODS)}")

    headers = config.get("headers", {})
    if not isinstance(headers, dict):
        errors.append("Field 'headers' must be a dictionary")
    else:
        for key, value in headers.items():
            if not isinstance(key, str) or not isinstance(value, str):
                errors.append("Header names and values must be strings")
            elif any(c in key + value for c in "\r\n"):
                errors.append(f"Header '{key}' must not contain line breaks")

    timeout = config.get("timeout", DEFAULT_TIMEOUT_SECONDS)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        errors.append("Field 'timeout' must be a positive number of seconds")

    response_path = config.get("response_path")
    if response_path is not None and (not isinstance(response_path, str) or not response_path.strip()):
        errors.append("Field 'response_path' must be a non-empty string")

    tool = config.get("tool")
    if not isinstance(tool, dict):
        errors.append("Missing required field: tool")
        return errors

    name = tool.get("name")
    if not isinstance(name, str) or not TOOL_NAME_PATTERN.match(name):
        errors.append("Field 'tool.name' must be 1-64 characters of letters, digits, '_' or '-'")
    if "description" in tool and not isinstance(tool["description"], str):
        errors.append("Field 'tool.description' must be a string")
    schema = tool.get("inputSchema")
    if not isinstance(schema, dict) or schema.get("type") != "object":
        errors.append("Field 'tool.inputSchema' must be a JSON schema with \"type\": \"object\"")
    elif not isinstance(schema.get("properties", {}), dict):
        errors.append("Field 'tool.inputSchema.properties' must be a dictionary")

    return errors


def resolve_headers(headers: Mapping[str, str], variables: Mapping[str, str]) -> Dict[str, str]:
    """
    Substitute ${VAR} references in header values.

    Raises ValueError naming the missing variable (never the header value,
    which may hold a partially resolved secret).
    """
    resolved = {}
    for key, value in headers.items():
        def substitute(match: re.Match) -> str:
            name = match.group(1)
            if name not in variables:
                raise ValueError(f"Header '{key}' references ${{{name}}}, which is not set")
            return variables[name]

        resolved[key] = VARIABLE_PATTERN.sub(substitute, value)
    return resolved


def extract_path(data: Any, path: str) -> Any:
    """Follow a dotted path such as 'choices.0.message.content'. Raises KeyError if missing."""
    current = data
    for part in path.split("."):
        if isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(part)
    return current


def _text_result(text: str, is_error: bool = False) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _rpc_result(request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _rpc_error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class ProxyHandle:
    """
    Registry entry for a running proxy MCP server.

    Stored in ServerManager.processes alongside subprocess handles, so it
    exposes the subset of the Popen interface the lifecycle code uses
    (poll/terminate/kill/wait/pid/returncode). There is no OS process: "running"
    means the handle has not been stopped.
    """

    transport = PROXY_TYPE
    pid = None

    def __init__(self, server_id: str, config: Mapping[str, Any], variables: Mapping[str, str]):
        errors = validate_proxy_config(config)
        if errors:
            raise ValueError("; ".join(errors))

        self.server_id = server_id
        self.endpoint = config["endpoint"]
        self.method = config.get("method", "POST").upper()
        self.headers = resolve_headers(config.get("headers", {}), variables)
        self.timeout = float(config.get("timeout", DEFAULT_TIMEOUT_SECONDS))
        self.response_path = config.get("response_path")
        self.tool = {
            "name": config["tool"]["name"],
            "description": config["tool"].get("description", ""),
            "inputSchema": config["tool"]["inputSchema"],
        }
        self.returncode: Optional[int] = None
        self._client = httpx.AsyncClient(timeout=self.timeout)

    # ── Popen-compatible lifecycle ────────────────────────────────────────

    def poll(self) -> Optional[int]:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = 0

    def kill(self) -> None:
        self.returncode = 0

    def wait(self, timeout: Optional[float] = None) -> int:
        return self.returncode

    async def aclose(self) -> None:
        await self._client.aclose()

    # ── MCP protocol ──────────────────────────────────────────────────────

    async def handle(self, request: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        """Answer one JSON-RPC request. Returns None for notifications."""
        if "id" not in request:
            return None

        request_id = request["id"]
        method = request.get("method")
        params = request.get("params")
        if not isinstance(params, dict):
            params = {}

        if method == "initialize":
            return _rpc_result(request_id, {
                "protocolVersion": params.get("protocolVersion", "2025-03-26"),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": self.server_id, "version": "1.0.0"},
            })
        if method == "ping":
            return _rpc_result(request_id, {})
        if method == "tools/list":
            return _rpc_result(request_id, {"tools": [self.tool]})
        if method == "tools/call":
            if params.get("name") != self.tool["name"]:
                return _rpc_error(request_id, -32602, f"Unknown tool: {params.get('name')}")
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                return _rpc_error(request_id, -32602, "Tool arguments must be an object")
            return _rpc_result(request_id, await self.call_upstream(arguments))

        return _rpc_error(request_id, -32601, f"Method not found: {method}")

    async def call_upstream(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Send the tool arguments to the endpoint and convert the reply to a tool result."""
        if self.method in QUERY_METHODS:
            if any(isinstance(v, dict) for v in arguments.values()):
                return _text_result(f"{self.method} arguments cannot contain objects", is_error=True)
            request_kwargs = {"params": arguments}
        else:
            request_kwargs = {"json": arguments}

        log = logger.bind(server_id=self.server_id)
        started = time.monotonic()
        try:
            response = await self._client.request(
                self.method, self.endpoint, headers=self.headers, **request_kwargs
            )
        except httpx.TimeoutException:
            log.warning(f"[proxy.timeout] {self.method} {self.endpoint} after {self.timeout}s")
            return _text_result(f"Upstream request timed out after {self.timeout:g}s", is_error=True)
        except httpx.RequestError as e:
            log.warning(f"[proxy.unreachable] {self.method} {self.endpoint}: {type(e).__name__}")
            return _text_result(f"Could not reach upstream endpoint: {type(e).__name__}", is_error=True)

        elapsed_ms = int((time.monotonic() - started) * 1000)
        log.info(f"[proxy.response] {self.method} {self.endpoint} status={response.status_code} elapsed={elapsed_ms}ms")

        if response.status_code >= 400:
            return _text_result(
                f"Upstream returned HTTP {response.status_code}: {response.text[:MAX_ERROR_BODY_CHARS]}",
                is_error=True,
            )

        if not self.response_path:
            return _text_result(response.text)

        try:
            value = extract_path(response.json(), self.response_path)
        except (ValueError, KeyError):
            return _text_result(
                f"Upstream response has no '{self.response_path}': {response.text[:MAX_ERROR_BODY_CHARS]}",
                is_error=True,
            )
        return _text_result(value if isinstance(value, str) else json.dumps(value))
