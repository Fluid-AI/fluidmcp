import time
import json
import asyncio
import ipaddress
from typing import Optional, Dict, Any
from urllib.parse import urlparse
import httpx
from loguru import logger


def _validate_url(url: str) -> None:
    """Block non-HTTP schemes and connections to private/internal network ranges."""
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError("Invalid URL")

    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are allowed")

    host = parsed.hostname or ""
    if not host:
        raise ValueError("URL must include a host")

    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return  # hostname, not a bare IP — DNS rebinding is out of scope

    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        raise ValueError("Connections to private/internal addresses are not allowed")


class InspectorSession:
    """
    Manages a temporary connection to an external MCP server for the inspector.

    Uses raw JSON-RPC over HTTP (for http transport) or SSE + HTTP POST
    (for sse transport). No MCP SDK required — matches FluidMCP's existing
    httpx-based pattern.

    For stdio transport, the server is assumed to be already running and
    accessible via a URL endpoint.
    """

    def __init__(
        self,
        url: str,
        transport: str,
        auth: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        timeout: int = 10000,
    ):
        self.url = url.rstrip("/")
        self.transport = transport.lower()
        self.auth = auth or {}
        self.extra_headers = headers or {}
        self.env_vars = env_vars or {}
        self.timeout = timeout / 1000  # Convert ms to seconds
        self.created_at = time.time()
        self.last_used = time.time()

        # For SSE: the endpoint to POST messages to (received during SSE handshake)
        self._sse_post_url: Optional[str] = None
        self._sse_session_id: Optional[str] = None

        # Shared httpx client for this session
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10.0, read=self.timeout, write=10.0, pool=10.0),
                follow_redirects=False,  # prevent redirect-based SSRF bypass
            )
        return self._client

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers including auth and any custom headers."""
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        # Add bearer token auth if configured
        auth_type = self.auth.get("type", "none")
        if auth_type == "bearer":
            token = self.auth.get("token", "")
            if token:
                headers["Authorization"] = f"Bearer {token}"

        # Merge any custom headers (these can override defaults)
        headers.update(self.extra_headers)
        return headers

    async def initialize(self) -> Dict[str, Any]:
        """
        Perform the MCP initialize handshake to verify the server is reachable
        and retrieve server info.

        Returns server info dict with name and version.
        Raises httpx.HTTPError or Exception on failure.
        """
        self.last_used = time.time()

        if self.transport == "sse":
            return await self._initialize_sse()
        else:
            # HTTP and stdio both use JSON-RPC POST
            return await self._initialize_http()

    async def _initialize_http(self) -> Dict[str, Any]:
        """Send MCP initialize JSON-RPC request over HTTP POST."""
        client = self._get_client()
        headers = self._build_headers()

        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "FluidMCP Inspector",
                    "version": "1.0.0"
                }
            }
        }

        response = await client.post(self.url, json=init_request, headers=headers)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise Exception(f"MCP initialize error: {data['error'].get('message', 'Unknown error')}")

        result = data.get("result", {})
        server_info = result.get("serverInfo", {})

        return {
            "name": server_info.get("name", "Unknown MCP Server"),
            "version": server_info.get("version", "unknown"),
            "protocol_version": result.get("protocolVersion", "unknown")
        }

    async def _initialize_sse(self) -> Dict[str, Any]:
        """
        Connect to SSE endpoint to get the POST messages URL,
        then send the initialize request via POST.

        MCP SSE pattern:
          1. GET /sse  → streams events, first event contains the endpoint URL
          2. POST {endpoint_url}  → send JSON-RPC messages
        """
        client = self._get_client()
        headers = self._build_headers()
        sse_headers = {**headers, "Accept": "text/event-stream"}

        # Determine SSE endpoint URL
        sse_url = self.url if self.url.endswith("/sse") else f"{self.url}/sse"

        # Connect to SSE and read the first event to get the messages endpoint
        endpoint_url = None
        try:
            async with client.stream("GET", sse_url, headers=sse_headers, timeout=10.0) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        data_str = line[len("data:"):].strip()
                        # MCP SSE servers send the messages endpoint URL as first data event
                        if data_str.startswith("/") or data_str.startswith("http"):
                            # Relative path — make it absolute
                            if data_str.startswith("/"):
                                parsed = urlparse(self.url)
                                endpoint_url = f"{parsed.scheme}://{parsed.netloc}{data_str}"
                            else:
                                endpoint_url = data_str
                            break
                        # Some servers send JSON with endpoint info
                        try:
                            event_data = json.loads(data_str)
                            if "endpoint" in event_data:
                                endpoint_url = event_data["endpoint"]
                                break
                        except json.JSONDecodeError:
                            pass
        except asyncio.TimeoutError:
            raise Exception("SSE connection timed out waiting for endpoint URL")

        if not endpoint_url:
            raise Exception("SSE server did not provide a messages endpoint URL")

        # Validate SSE-derived endpoint URL — attacker-controlled SSE stream could
        # inject an internal address here, bypassing the initial _validate_mcp_url check.
        _validate_url(endpoint_url)

        # Enforce same-host: endpoint must be on the same origin as the SSE URL
        origin_host = urlparse(self.url).netloc
        endpoint_host = urlparse(endpoint_url).netloc
        if origin_host != endpoint_host:
            raise ValueError(
                f"SSE endpoint host '{endpoint_host}' does not match origin '{origin_host}'"
            )

        self._sse_post_url = endpoint_url
        logger.debug(f"SSE messages endpoint: {endpoint_url}")

        # Now send initialize via POST to the messages endpoint
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "FluidMCP Inspector",
                    "version": "1.0.0"
                }
            }
        }

        response = await client.post(endpoint_url, json=init_request, headers=headers)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise Exception(f"MCP initialize error: {data['error'].get('message', 'Unknown error')}")

        result = data.get("result", {})
        server_info = result.get("serverInfo", {})

        return {
            "name": server_info.get("name", "Unknown MCP Server"),
            "version": server_info.get("version", "unknown"),
            "protocol_version": result.get("protocolVersion", "unknown")
        }

    def _get_post_url(self) -> str:
        """Get the URL to POST JSON-RPC messages to."""
        if self.transport == "sse" and self._sse_post_url:
            return self._sse_post_url
        return self.url

    async def list_tools(self) -> list:
        """Fetch the list of tools available on the MCP server."""
        self.last_used = time.time()
        client = self._get_client()
        headers = self._build_headers()
        post_url = self._get_post_url()

        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }

        response = await client.post(post_url, json=request, headers=headers)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise Exception(f"tools/list error: {data['error'].get('message', 'Unknown error')}")

        return data.get("result", {}).get("tools", [])

    async def call_tool(self, name: str, params: Dict[str, Any]) -> Any:
        """Execute a tool on the MCP server."""
        self.last_used = time.time()
        client = self._get_client()
        headers = self._build_headers()
        post_url = self._get_post_url()

        request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": params
            }
        }

        response = await client.post(post_url, json=request, headers=headers)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise Exception(f"tools/call error: {data['error'].get('message', 'Unknown error')}")

        return data.get("result", {})

    async def close(self):
        """Close the httpx client."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None