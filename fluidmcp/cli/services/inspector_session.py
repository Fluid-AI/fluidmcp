import time
import json
import asyncio
import ipaddress
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
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

    HTTP transport: raw JSON-RPC POST, response comes back in the same HTTP response.
    SSE transport:  persistent GET /sse connection (background task) receives all
                    responses; requests are sent via POST to the messages endpoint.
                    This matches the MCP SSE spec — the stream must stay open.
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
        self.timeout = timeout / 1000  # ms → seconds
        self.created_at = time.time()
        self.last_used = time.time()

        self.logs: List[Dict[str, Any]] = []

        # Auto-incrementing request ID (avoids hardcoded 1/2/3 collisions)
        self._req_id = 0

        # SSE state
        self._sse_post_url: Optional[str] = None
        self._sse_ready = asyncio.Event()      # set once endpoint URL is known
        self._sse_pending: Dict[int, "asyncio.Future[dict]"] = {}  # id → Future
        self._sse_task: Optional[asyncio.Task] = None

        # Shared httpx client for HTTP/POST requests
        self._client: Optional[httpx.AsyncClient] = None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(connect=10.0, read=self.timeout, write=10.0, pool=10.0),
                follow_redirects=False,
            )
        return self._client

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.auth.get("type") == "bearer" and self.auth.get("token"):
            headers["Authorization"] = f"Bearer {self.auth['token']}"
        headers.update(self.extra_headers)
        return headers

    MAX_LOGS = 250

    def add_log(self, log_type: str, message: str) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": log_type,
            "message": message,
        }
        self.logs.append(entry)
        if len(self.logs) > self.MAX_LOGS:
            self.logs.pop(0)
        logger.debug(f"Inspector log [{log_type}]: {message}")

    # ── SSE persistent listener ───────────────────────────────────────────────

    async def _sse_listener(self) -> None:
        """
        Background task: holds the GET /sse connection open for the entire session.

        - First data event   → the POST messages endpoint URL (signals _sse_ready)
        - Subsequent events  → JSON-RPC responses, routed to waiting callers via Futures
        """
        sse_url = self.url if self.url.endswith("/sse") else f"{self.url}/sse"
        sse_headers = {**self._build_headers(), "Accept": "text/event-stream"}

        # Dedicated client with no read timeout — this stream stays open indefinitely
        sse_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0),
            follow_redirects=False,
        )
        try:
            async with sse_client.stream("GET", sse_url, headers=sse_headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if not data_str:
                        continue

                    # ── First event: endpoint URL ──────────────────────────
                    if self._sse_post_url is None:
                        endpoint_url: Optional[str] = None
                        if data_str.startswith("/") or data_str.startswith("http"):
                            if data_str.startswith("/"):
                                p = urlparse(self.url)
                                endpoint_url = f"{p.scheme}://{p.netloc}{data_str}"
                            else:
                                endpoint_url = data_str
                        else:
                            try:
                                ev = json.loads(data_str)
                                if "endpoint" in ev:
                                    endpoint_url = ev["endpoint"]
                            except json.JSONDecodeError:
                                pass

                        if endpoint_url:
                            try:
                                _validate_url(endpoint_url)
                            except ValueError as e:
                                raise Exception(f"SSE endpoint rejected: {e}")

                            base_host = urlparse(self.url).netloc
                            ep_host = urlparse(endpoint_url).netloc
                            if ep_host and ep_host != base_host:
                                raise Exception(
                                    f"SSE endpoint host mismatch — "
                                    f"expected {base_host}, got {ep_host}"
                                )

                            self._sse_post_url = endpoint_url
                            self._sse_ready.set()
                            logger.debug(f"SSE messages endpoint: {endpoint_url}")
                        continue

                    # ── Subsequent events: JSON-RPC responses ──────────────
                    try:
                        msg = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    req_id = msg.get("id")
                    if req_id is not None:
                        future = self._sse_pending.pop(req_id, None)
                        if future and not future.done():
                            future.set_result(msg)

        except asyncio.CancelledError:
            pass  # normal shutdown
        except Exception as e:
            logger.warning(f"SSE listener terminated: {e}")
            # Unblock any callers waiting on futures
            for fut in self._sse_pending.values():
                if not fut.done():
                    fut.set_exception(e)
            self._sse_pending.clear()
            if not self._sse_ready.is_set():
                self._sse_ready.set()
        finally:
            await sse_client.aclose()

    async def _sse_request(self, request: dict) -> dict:
        """POST a request and await the response that comes back on the SSE stream."""
        await asyncio.wait_for(self._sse_ready.wait(), timeout=10.0)

        if not self._sse_post_url:
            raise Exception("SSE session not ready — no endpoint URL")

        req_id = request["id"]
        loop = asyncio.get_event_loop()
        future: "asyncio.Future[dict]" = loop.create_future()
        self._sse_pending[req_id] = future

        try:
            client = self._get_client()
            resp = await client.post(
                self._sse_post_url, json=request, headers=self._build_headers()
            )
            resp.raise_for_status()
            # Server responds 202 Accepted; actual result arrives via SSE stream
            return await asyncio.wait_for(future, timeout=self.timeout)
        except Exception:
            self._sse_pending.pop(req_id, None)
            if not future.done():
                future.cancel()
            raise

    # ── Transport dispatcher ──────────────────────────────────────────────────

    def _make_request(self, method: str, params: dict) -> dict:
        return {"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params}

    async def _send(self, request: dict) -> dict:
        """Route request through SSE or plain HTTP depending on transport."""
        if self.transport == "sse":
            return await self._sse_request(request)

        client = self._get_client()
        response = await client.post(self.url, json=request, headers=self._build_headers())
        response.raise_for_status()
        return response.json()

    # ── Public API ────────────────────────────────────────────────────────────

    async def initialize(self) -> Dict[str, Any]:
        self.last_used = time.time()

        if self.transport == "sse":
            # Kick off the background SSE listener before sending any requests
            loop = asyncio.get_event_loop()
            self._sse_task = loop.create_task(self._sse_listener())

        init_request = self._make_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "extensions": {
                    "io.modelcontextprotocol/ui": {
                        "mimeTypes": ["text/html+mcp", "text/html;profile=mcp-app"]
                    }
                }
            },
            "clientInfo": {"name": "FluidMCP Inspector", "version": "1.0.0"},
        })

        data = await self._send(init_request)

        if "error" in data:
            raise Exception(f"MCP initialize error: {data['error'].get('message', 'Unknown error')}")

        result = data.get("result", {})
        server_info = result.get("serverInfo", {})
        info = {
            "name": server_info.get("name", "Unknown MCP Server"),
            "version": server_info.get("version", "unknown"),
            "protocol_version": result.get("protocolVersion", "unknown"),
        }

        self.add_log("connect", f"Connected to {info['name']} ({self.transport.upper()})")
        return info

    async def list_tools(self) -> list:
        self.last_used = time.time()
        data = await self._send(self._make_request("tools/list", {}))
        if "error" in data:
            raise Exception(f"tools/list error: {data['error'].get('message', 'Unknown error')}")
        return data.get("result", {}).get("tools", [])

    async def call_tool(self, name: str, params: Dict[str, Any]) -> Any:
        self.last_used = time.time()
        self.add_log("tool_call", f"Running tool: {name}")
        try:
            data = await self._send(
                self._make_request("tools/call", {"name": name, "arguments": params})
            )
            if "error" in data:
                msg = data["error"].get("message", "Unknown error")
                self.add_log("tool_error", f"Tool '{name}' failed: {msg}")
                raise Exception(f"tools/call error: {msg}")
            self.add_log("tool_result", f"Tool '{name}' executed successfully")
            return data.get("result", {})
        except Exception as e:
            if not self.logs or self.logs[-1]["type"] != "tool_error":
                self.add_log("tool_error", f"Tool '{name}' error: {str(e)}")
            raise

    async def list_resources(self) -> list:
        self.last_used = time.time()
        data = await self._send(self._make_request("resources/list", {}))
        if "error" in data:
            raise Exception(f"resources/list error: {data['error'].get('message', 'Unknown error')}")
        return data.get("result", {}).get("resources", [])

    async def read_resource(self, uri: str) -> dict:
        self.last_used = time.time()
        data = await self._send(self._make_request("resources/read", {"uri": uri}))
        if "error" in data:
            raise Exception(f"resources/read error: {data['error'].get('message', 'Unknown error')}")
        contents = data.get("result", {}).get("contents", [])
        return contents[0] if contents else {}

    async def close(self) -> None:
        self.add_log("disconnect", "Session closed")
        if self._sse_task:
            self._sse_task.cancel()
            try:
                await self._sse_task
            except (asyncio.CancelledError, Exception):
                pass
            self._sse_task = None
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
