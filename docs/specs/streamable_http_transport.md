# Spec: Streamable-HTTP Transport for MCP Servers

**Branch:** `http_streamable_spec`
**Status:** Draft

---

## 1. Context and Problem Statement

The current stdio transport model uses one `asyncio.Lock` per MCP server subprocess
(`_io_locks` dict in `package_launcher.py:353-358`). Every request must:

1. Acquire the lock
2. Write JSON-RPC to `process.stdin`
3. Block on `process.stdout.readline()`
4. Release the lock

This serialises all requests to a single server. With 50 concurrent users, request 50
waits behind 49 others — latency grows linearly with concurrency. Beyond ~5-10 concurrent
users per server, queue times become noticeable. The lock also does not release on client
disconnect, so abandoned requests continue to hold the queue.

**Why streamable-http instead of SSE?**

SSE requires two coordinated channels (GET `/sse` + POST `/messages/`), long-lived
connections, and event-correlation logic. Streamable-http is a single `POST /mcp`
endpoint — each request is a self-contained HTTP round-trip. No lock is needed on the
FluidMCP gateway side because each request becomes an independent `httpx.post()` call
that FastMCP's async event loop handles concurrently.

---

## 2. How Streamable-HTTP Works

When an MCP server calls `mcp.run(transport="streamable-http")`, FastMCP starts a
Uvicorn HTTP server inside the subprocess bound to a port. It exposes:

```
POST /mcp   — JSON-RPC request body → JSON (or SSE-stream) response body
```

Simple tool calls return plain JSON. Long-running operations may return an SSE stream
embedded in the response body. Because it is standard HTTP, multiple requests arrive
concurrently. FastMCP's async event loop handles them: async tool functions run
concurrently, sync tool functions are offloaded to a thread pool.

FluidMCP's gateway proxies each request with a fire-and-forget `httpx.post()` — no
lock, no serialisation.

---

## Architecture Flow

### Server Startup

```
                 ┌─────────────────────────────┐
                 │    fluidmcp serve / run      │
                 └──────────────┬──────────────┘
                                │
                                ▼
                 ┌─────────────────────────────┐
                 │   _spawn_mcp_process(id)     │
                 └──────────────┬──────────────┘
                                │
                         [transport?]
                                │
           ┌────────────────────┴───────────────────────┐
           │                                            │
        "stdio"                              "streamable-http"
           │                                            │
           ▼                                            ▼
┌──────────────────────┐                ┌───────────────────────────┐
│ Popen(stdin=PIPE,    │                │ _allocate_port()          │
│       stdout=PIPE)   │                │ find_free_port(8500,8600) │
└──────────┬───────────┘                └──────────────┬────────────┘
           │                                           │
           ▼                                           ▼
┌──────────────────────┐                ┌───────────────────────────┐
│ initialize_mcp_      │                │ env["MCP_PORT"] = port    │
│ server()             │                └──────────────┬────────────┘
│ JSON-RPC via stdin   │                               │
└──────────┬───────────┘                               ▼
           │                            ┌───────────────────────────┐
           ▼                            │ Popen(env=env)            │
┌──────────────────────┐                └──────────────┬────────────┘
│ _discover_and_cache_ │                               │
│ tools()              │                               ▼
│ stdin tools/list     │                  poll POST /mcp initialize
└──────────┬───────────┘                  every 1 s · max 30 s
           │                                          │
           ▼                              ┌───────────┴───────────┐
┌──────────────────────┐                  │                       │
│ subprocess           │               timeout /              200 OK
│ registered in        │               process died              │
│ processes{}          │                  │                       ▼
└──────────────────────┘                  ▼           ┌──────────────────────┐
                                    discard port      │ _discover_and_cache_ │
                                    return None       │ tools()              │
                                    (server=failed)   │ POST /mcp tools/list │
                                                      └──────────┬───────────┘
                                                                 │
                                                                 ▼
                                                      ┌──────────────────────┐
                                                      │ HttpSubprocessHandle │
                                                      │ registered in        │
                                                      │ processes{}          │
                                                      └──────────────────────┘
```

### Request Proxy

```
       ┌────────────────────────────────────────┐
       │   Client: POST /{server_name}/mcp      │
       └──────────────────┬─────────────────────┘
                          │
                          ▼
       ┌────────────────────────────────────────┐
       │  proxy_jsonrpc()                       │
       │  (create_dynamic_router)               │
       └──────────────────┬─────────────────────┘
                          │
               [server in processes?]
                    ┌─────┴──────┐
                 No │            │ Yes
                    ▼            │
                HTTP 404         ▼
                       [process.poll() is None?]
                             ┌───┴────────┐
                        dead │            │ alive
                             ▼            │
                          HTTP 503        ▼
                               [HttpSubprocessHandle?]
                                  ┌───────┴──────────────────┐
                               No │                          │ Yes
                                  ▼                          ▼
                            ── STDIO ──           [process.transport?]
                                  │                          │
                           acquire lock          ┌───────────┴──────────────┐
                           write to stdin        │                          │
                           readline stdout     "sse"          "streamable-http"
                           release lock          │                          │
                                  │              ▼                          ▼
                                  │    POST base_url               POST base_url/mcp
                                  │    /messages/                  (no lock needed)
                                  │              │                          │
                                  └──────────────┴──────────────────────────┘
                                                 │
                                                 ▼
                                          JSONResponse
```

---

## 3. MCP Server Convention

All Python MCP servers must read their port from `MCP_PORT`, falling back to `8000`:

```python
import os
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("MyServer")

# ... tool definitions ...

if __name__ == "__main__":
    port = int(os.environ.get("MCP_PORT", "8000"))
    mcp.run(transport="streamable-http", host="127.0.0.1", port=port)
```

**Rules:**
- No hardcoded ports in server code.
- FluidMCP owns port assignment via `MCP_PORT` environment variable.
- All future MCP servers are Python-only (streamable-http is a Python/FastMCP feature).

---

## 4. Port Management

### Subprocess port range

`8500–8599` (exclusive upper bound: `find_free_port(8500, 8600, ...)`). Capacity: 100
concurrent HTTP-transport servers.

### In-memory port registry

`ServerManager` gains two new members:

| Member | Type | Purpose |
|--------|------|---------|
| `_allocated_ports` | `Set[int]` | Ports currently in use by live subprocesses |
| `_allocate_port()` | method | Picks the next free port and adds it to the set |

`_allocate_port()` calls `find_free_port(8500, 8600, taken_ports=self._allocated_ports)`
(defined in `network_utils.py:69`). `find_free_port` already checks both the in-memory
set and actual socket availability via `is_port_in_use()`, which guards against orphan
processes from a previous crash.

On server stop or delete, the port is removed from `_allocated_ports`.

### No MongoDB persistence

Port assignments are purely runtime state. On FluidMCP restart the set starts empty;
ports are freshly allocated as servers relaunch. `is_port_in_use()` acts as the safety
net during allocation if orphan processes are still bound to ports.

### Applies to both HTTP transports

Both `"sse"` and `"streamable-http"` transports use this unified port allocation. The
existing `"url"` field in SSE configs is dropped; FluidMCP constructs the internal URL
from the allocated port.

---

## 5. FluidMCP Codebase Changes

### 5.1 `sse_handle.py` → Generalise to `HttpSubprocessHandle`

**File:** `fluidmcp/cli/services/sse_handle.py`

Rename `SseSubprocessHandle` → `HttpSubprocessHandle`. Replace the `sse_url` attribute
with `base_url`. Add a `transport` field (`"sse"` or `"streamable-http"`).

```python
class HttpSubprocessHandle:
    def __init__(self, process: subprocess.Popen, base_url: str, transport: str):
        self._process = process
        self.base_url = base_url          # e.g. "http://127.0.0.1:8542"
        self.transport = transport        # "sse" or "streamable-http"

    # pid, returncode, poll, terminate, kill, wait — unchanged
```

`sse_url` is kept as a **read-only property** returning `base_url` for one release to
avoid breaking any external callers, then removed.

Update every `isinstance(process, SseSubprocessHandle)` check in:
- `package_launcher.py:400`, `479`, `581` — replace class reference
- Any other files that import `SseSubprocessHandle`

### 5.2 `server_manager.py` — Port allocation and streamable-http handshake

**File:** `fluidmcp/cli/services/server_manager.py`

#### 5.2.1 New members on `ServerManager.__init__` (line ~28)

```python
self._allocated_ports: Set[int] = set()
```

#### 5.2.2 New `_allocate_port()` method

```python
def _allocate_port(self) -> int:
    from .network_utils import find_free_port
    port = find_free_port(8500, 8600, taken_ports=self._allocated_ports)
    self._allocated_ports.add(port)
    return port
```

#### 5.2.3 New `_handshake_streamable_http_subprocess()` method

Analogous to the existing `_handshake_sse_subprocess()` (line 980), but simpler —
no streaming GET, just HTTP POSTs:

```python
async def _handshake_streamable_http_subprocess(
    self,
    id: str,
    config: Dict[str, Any],
    process: subprocess.Popen,
    port: int,
) -> Optional[HttpSubprocessHandle]:
    """
    Wait for a streamable-http MCP subprocess to accept connections,
    then discover and cache tools.

    Polls POST http://127.0.0.1:<port>/mcp with a JSON-RPC initialize
    request until the server responds (max 30 s timeout).
    """
```

Poll interval: 1 s. On first `200` response: call
`_discover_and_cache_tools_streamable_http(id, base_url)`. Return
`HttpSubprocessHandle(process, base_url, "streamable-http")` on success; `None` on
timeout or process death.

#### 5.2.4 New `_discover_and_cache_tools_streamable_http()` method

```python
async def _discover_and_cache_tools_streamable_http(
    self, server_id: str, base_url: str
) -> None:
```

Sends `POST {base_url}/mcp` with `{"jsonrpc":"2.0","id":1,"method":"tools/list"}` and
caches the result — mirrors `_discover_and_cache_tools_sse()` (line 1055) but targets
`/mcp` instead of `/messages/`.

#### 5.2.5 Transport branch in `_spawn_mcp_process()` (line 874)

Extend the existing transport branch:

```python
# Current (line 874):
if config.get("transport") == "sse":
    handle = await self._handshake_sse_subprocess(id, config, process)
    ...

# New:
transport = config.get("transport", "stdio")

if transport == "sse":
    port = self._allocate_port()
    env["MCP_PORT"] = str(port)
    # re-spawn process with updated env (or inject before original spawn)
    handle = await self._handshake_sse_subprocess(id, config, process)
    ...

elif transport == "streamable-http":
    port = self._allocate_port()
    env["MCP_PORT"] = str(port)
    # re-spawn process with updated env (or inject before original spawn)
    handle = await self._handshake_streamable_http_subprocess(
        id, config, process, port
    )
    if not handle:
        self._allocated_ports.discard(port)
        ...
    return handle
```

> **Note:** Port allocation must happen **before** `subprocess.Popen` is called so
> `MCP_PORT` is in the environment at process start. The `_allocate_port()` call should
> be placed in the pre-spawn env-building block (around line 788).

#### 5.2.6 Port cleanup on stop/delete

In `stop_server()` and anywhere else that calls `process.kill()` / `process.terminate()`
for an `HttpSubprocessHandle`:

```python
if isinstance(process, HttpSubprocessHandle):
    port = int(process.base_url.split(":")[-1])
    self._allocated_ports.discard(port)
```

### 5.3 `package_launcher.py` — Streamable-http proxy

**File:** `fluidmcp/cli/services/package_launcher.py`

#### 5.3.1 New `_proxy_to_streamable_http()` function

```python
async def _proxy_to_streamable_http(
    base_url: str, payload: dict, timeout: float = 60.0
) -> dict:
    """
    Forward a JSON-RPC request to a streamable-http MCP server via POST /mcp.
    Simpler than _proxy_to_sse_server — no SSE stream coordination.
    """
    mcp_url = f"{base_url.rstrip('/')}/mcp"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(mcp_url, json=payload)
        resp.raise_for_status()
        return resp.json()
    # raise HTTPException on httpx errors (same pattern as _proxy_to_sse_server)
```

No `asyncio.Lock` — each call is an independent HTTP round-trip.

#### 5.3.2 Update `proxy_jsonrpc` (line 400)

Replace the current `isinstance(process, SseSubprocessHandle)` block with a
transport-aware branch:

```python
if isinstance(process, HttpSubprocessHandle):
    if process.transport == "streamable-http":
        response = await _proxy_to_streamable_http(process.base_url, request)
    else:  # "sse"
        response = await _proxy_to_sse_server(process.base_url, request)
    return JSONResponse(content=response)
```

#### 5.3.3 Update `list_tools` (line 581)

Same pattern — branch on `process.transport` inside the `isinstance(process, HttpSubprocessHandle)` block.

### 5.4 `management.py` — MCP proxy endpoint for serve mode

**File:** `fluidmcp/cli/api/management.py`

Add a new endpoint alongside the existing SSE proxy endpoints:

```python
@router.post("/api/servers/{id}/mcp")
async def proxy_mcp_request(
    id: str,
    request: Request,
    token: str = Depends(get_token),
    server_manager = Depends(get_server_manager),
):
    """
    Reverse-proxy a streamable-http JSON-RPC request to a running server.
    Counterpart to the SSE endpoints /api/servers/{id}/sse and
    /api/servers/{id}/messages.
    """
    process = server_manager.processes.get(id)
    if not process:
        raise HTTPException(404, f"Server '{id}' not found or not running")
    if not isinstance(process, HttpSubprocessHandle) or process.transport != "streamable-http":
        raise HTTPException(400, f"Server '{id}' does not use streamable-http transport")

    body = await request.json()
    mcp_url = f"{process.base_url.rstrip('/')}/mcp"

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(mcp_url, json=body)

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )
```

### 5.5 `server_builder.py` — Transport detection

**File:** `fluidmcp/cli/services/server_builder.py`

Extend the transport detection block (line 136) to include `"streamable-http"`:

```python
transport = server_config.get("transport", "stdio")

config = { ... }  # existing fields

if transport in ("sse", "streamable-http"):
    config["transport"] = transport
    # No "url" field — FluidMCP allocates the port at runtime
    logger.info(f"Server '{server_id}' configured with {transport} transport")
```

Remove the `sse_url = server_config.get("url", "http://127.0.0.1:8000")` default and
the `config["url"] = sse_url` assignment. The URL is now constructed from the
dynamically allocated port, not stored in config.

### 5.6 `inspector_session.py` — Streamable-http code path

**File:** `fluidmcp/cli/services/inspector_session.py`

In `initialize()` (line 113), add `"streamable-http"` to the HTTP branch:

```python
async def initialize(self) -> Dict[str, Any]:
    if self.transport == "sse":
        server_info = await self._initialize_sse()
    else:
        # Handles "http", "stdio", and "streamable-http"
        # All three use: POST <url> with JSON-RPC initialize body
        server_info = await self._initialize_http()
```

For `"streamable-http"`, `self.url` should be the `/mcp` endpoint
(e.g. `http://127.0.0.1:8542/mcp`). No changes needed in `_initialize_http()` itself —
it already does `POST self.url`.

In `_get_post_url()` (line 261), no change needed — for `"streamable-http"` the URL
passed to the constructor already includes `/mcp`.

Update the `add_log` transport label in `initialize()` so it correctly shows
`STREAMABLE-HTTP` instead of lumping it with `HTTP`.

### 5.7 Frontend — Transport indicator (non-blocking)

Display-only change on the server status card: show `stdio`, `sse`, or
`streamable-http` as a badge. Assigned to Shubhendu. Not on the critical path.

---

## 6. User-Facing Config Change

### Before (SSE — requires manual port and URL)

```json
{
  "mcpServers": {
    "my-server": {
      "command": "python",
      "args": ["server.py"],
      "transport": "sse",
      "url": "http://127.0.0.1:8001",
      "env": {}
    }
  }
}
```

### After (streamable-http — no port, no URL)

```json
{
  "mcpServers": {
    "my-server": {
      "command": "python",
      "args": ["server.py"],
      "transport": "streamable-http",
      "env": {}
    }
  }
}
```

SSE servers also adopt this same simplified shape going forward — the `"url"` field is
no longer accepted for either HTTP transport. FluidMCP allocates the port and constructs
the internal URL at runtime.

**Migration:** Any existing SSE config with an explicit `"url"` field will have that
field silently ignored once port allocation is in place. A one-time warning log is
acceptable.

---

## 7. Task Ordering and Dependencies

```
Phase 1 — No-op prep
  1.1  Rename SseSubprocessHandle → HttpSubprocessHandle (sse_handle.py)
       Update all isinstance() checks in package_launcher.py
       [No behaviour change — sse_url kept as alias property]

Phase 2 — Port allocation (prerequisite for Phase 3)
  2.1  Add _allocated_ports + _allocate_port() to ServerManager
  2.2  Inject MCP_PORT into subprocess env for "sse" transport
       (validates the allocation plumbing without changing any proxy logic)

Phase 3 — Streamable-http support (critical path: each step depends on the previous)
  3.1  Add _handshake_streamable_http_subprocess() to ServerManager   ← depends on 2.x
  3.2  Add _discover_and_cache_tools_streamable_http() to ServerManager
  3.3  Add transport branch in _spawn_mcp_process() for "streamable-http"
  3.4  Add _proxy_to_streamable_http() to package_launcher.py
  3.5  Update proxy_jsonrpc / list_tools / sse_stream in create_dynamic_router()
  3.6  Add POST /api/servers/{id}/mcp to management.py

Non-blocking (parallelisable once 3.1 is merged):
  3.7  server_builder.py — drop "url" field, add "streamable-http" to transport detection
  3.8  inspector_session.py — add "streamable-http" code path in initialize()
  3.9  Frontend — transport badge on server status card
```

---

## 8. Acceptance Criteria

| # | Criterion |
|---|-----------|
| 1 | A Python MCP server using `mcp.run(transport="streamable-http")` starts successfully via `fluidmcp serve` and appears as `running` |
| 2 | `POST /{server_name}/mcp` returns the correct JSON-RPC response |
| 3 | 50 concurrent requests to the same streamable-http server complete without serialisation delay (no `asyncio.Lock`) |
| 4 | Port is in range `8500–8599` and is removed from `_allocated_ports` on server stop |
| 5 | A config with `"transport": "streamable-http"` and **no** `"url"` field starts without error |
| 6 | A config with `"transport": "sse"` and **no** `"url"` field also starts correctly (port auto-allocated) |
| 7 | `POST /api/servers/{id}/mcp` proxies correctly to a streamable-http server |
| 8 | `InspectorSession` connects and lists tools for a streamable-http server |
| 9 | FluidMCP restart allocates fresh ports; no port collision with orphan processes |

---

## 9. Out of Scope

- Non-Python MCP servers (streamable-http is Python/FastMCP only).
- Persistent port assignments in MongoDB.
- Any changes to the stdio transport path.
- SSE transport protocol changes (only port allocation is affected).
