# MCP Server Architecture in FluidMCP: Complete Analysis

## Table of Contents
1. [MCP Server Definition](#1-mcp-server-definition)
2. [Tool Definition & JSON Schema](#2-tool-definition--json-schema)
3. [Communication Protocol](#3-communication-protocol)
4. [Tool Execution Flow](#4-tool-execution-flow)
5. [Server Lifecycle Management](#5-server-lifecycle-management)
6. [Error Handling](#6-error-handling)

---

## 1. MCP Server Definition

### What Makes Something an MCP Server?

An MCP server in FluidMCP is any executable process that:

1. **Implements the Model Context Protocol (MCP) JSON-RPC 2.0 interface**
   - Understands MCP protocol version: `2024-11-05`
   - Responds to standard MCP methods: `initialize`, `tools/list`, `tools/call`, `resources/list`, etc.

2. **Communicates via one of two transport mechanisms:**
   - **stdio** (default): JSON-RPC messages over stdin/stdout
   - **SSE** (Server-Sent Events): JSON-RPC over HTTP

3. **Is defined in a configuration format** that FluidMCP can resolve and execute

### metadata.json Structure

FluidMCP uses a **three-layer architecture** for metadata:

#### Layer 1: Input Layer (User-Facing)

Users can define MCP servers in **three formats**:

**Format 1: Direct Server Configuration (Recommended for testing)**
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
      "env": {
        "API_KEY": "optional-value"
      }
    }
  }
}
```
- Runs immediately without installation
- FluidMCP creates temporary metadata in `.fmcp-packages/.temp_servers/`
- Ideal for development and testing

**Format 2: GitHub Repository**
```json
{
  "github_token": "default-token-for-all-servers",
  "mcpServers": {
    "python-server": {
      "github_repo": "owner/repo",
      "github_token": "optional-per-server-token",
      "branch": "main",
      "command": "uv",
      "args": ["run", "server.py"],
      "env": {}
    }
  }
}
```
- Clones repositories to `.fmcp-packages/owner/repo/branch/`
- Automatically extracts metadata from README if metadata.json doesn't exist
- Can specify explicit commands or auto-detect from README
- Supports both default and per-server GitHub tokens

**Format 3: Package String (Requires FluidMCP Registry)**
```json
{
  "mcpServers": {
    "filesystem": "Author/Package@version"
  }
}
```
- Requires installation from registry
- Packages install to `.fmcp-packages/Author/Package/Version/`
- Each package has a `metadata.json` with MCP server configuration

#### Layer 2: Resolution Layer (Internal Processing)

FluidMCP normalizes all input formats through `config_resolver.py`:

```python
# fluidmcp/cli/services/config_resolver.py
def resolve_from_file(path: str, github_token: str = None) -> Dict[str, Any]:
    """
    Unified config resolution from multiple sources:
    - Direct configs: Creates temp metadata
    - Package strings: Downloads and installs packages
    - GitHub repos: Clones and prepares repositories
    """
```

Key resolution steps:
1. **_handle_github_server()** - Clones GitHub repos with authentication
2. **extract_or_create_metadata()** - Extracts metadata from README or uses existing
3. **_create_temp_server_dir()** - Creates temp metadata for direct configs
4. **Port assignment** - Assigns unique ports (8090 for single, 8099 for unified)
5. **install_path injection** - Sets working directory for execution

#### Layer 3: Runtime Metadata (Executable Truth)

After resolution, all servers converge to this canonical structure:

```json
{
  "mcpServers": {
    "server-name": {
      "command": "string",           // Required: Executable path
      "args": ["string"],             // Required: Command arguments
      "env": {"KEY": "value"},        // Optional: Environment variables
      "port": 8090,                   // Auto-injected: Unique port
      "install_path": "/path/to/dir", // Auto-injected: Installation path
      "transport": "stdio",           // Optional: "stdio" (default) or "sse"
      "url": "http://127.0.0.1:8000"  // Required if transport="sse"
    }
  }
}
```

**Critical Fields:**
- `port` and `install_path` are **never** provided by users—injected during resolution
- `transport` defaults to `"stdio"` if not specified
- `url` is required only for SSE transport servers

### Validation Rules

From `docs/metadata-schema.md`:

**Structural Validation:**
- `mcpServers` must exist and be an object
- Server names must be strings
- Invalid JSON results in immediate failure

**Direct Configuration Validation:**
- `command` is **required**
- `args` must be an array (defaults to `[]` if missing)
- `env` must be an object if provided
- Environment variables with placeholder patterns (e.g., `<your-api-key>`) are skipped with warnings

**GitHub Repository Validation:**
- `github_repo` must be in `owner/repo` format
- `branch` defaults to `main` if not specified
- Supports both per-server and default GitHub tokens

---

## 2. Tool Definition & JSON Schema

### MCP Tool Discovery Protocol

Tools are discovered via the MCP `tools/list` method during server initialization:

```json
// Request (sent by FluidMCP)
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list"
}

// Response (from MCP server)
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "read_file",
        "description": "Read contents of a file",
        "inputSchema": {
          "type": "object",
          "properties": {
            "path": {
              "type": "string",
              "description": "File path to read"
            }
          },
          "required": ["path"]
        }
      }
    ]
  }
}
```

### Tool Schema Structure

Every MCP tool follows this JSON schema:

```typescript
interface Tool {
  name: string;              // Unique identifier for the tool
  description: string;       // Human-readable description
  inputSchema: {             // JSON Schema defining inputs
    type: "object";
    properties: {
      [key: string]: {
        type: string;        // "string", "number", "boolean", "array", "object"
        description: string; // Parameter description
        enum?: any[];        // Optional: Allowed values
        items?: object;      // For array types
      };
    };
    required?: string[];     // List of required parameters
  };
}
```

### Tool Caching

FluidMCP caches discovered tools in the database (from `server_manager.py:885-930`):

```python
async def _discover_and_cache_tools(self, server_id: str, process: subprocess.Popen) -> None:
    """
    Discover tools via MCP list_tools and cache in database.
    """
    tools_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list"
    }
    
    process.stdin.write(json.dumps(tools_request) + "\n")
    process.stdin.flush()
    
    response_line = await asyncio.wait_for(
        asyncio.to_thread(process.stdout.readline),
        timeout=5.0
    )
    
    response = json.loads(response_line.strip())
    
    if "result" in response and "tools" in response["result"]:
        tools = response["result"]["tools"]
        
        # Cache tools in database
        config = await self.db.get_server_config(server_id)
        config["tools"] = tools
        await self.db.save_server_config(config)
        logger.info(f"Discovered and cached {len(tools)} tools")
```

**Tool Lifecycle:**
1. Server starts → FluidMCP sends `tools/list` request
2. Server responds with tool definitions
3. Tools are cached in database for fast access
4. Tools are available via REST API at `GET /{server}/mcp/tools/list`

---

## 3. Communication Protocol

FluidMCP supports **two transport mechanisms** for communication with MCP servers:

### 3.1 stdio Transport (Default)

**How it works:**
- MCP server process is spawned with stdin/stdout/stderr pipes
- JSON-RPC messages are sent via **stdin** (one message per line)
- JSON-RPC responses are received via **stdout** (one response per line)
- Logs/errors are sent to **stderr**

**Implementation** (from `package_launcher.py:213-226`):

```python
process = subprocess.Popen(
    stdio_command,
    cwd=working_dir,
    stdin=subprocess.PIPE,   # Write JSON-RPC requests here
    stdout=subprocess.PIPE,  # Read JSON-RPC responses here
    stderr=subprocess.PIPE,  # Server logs/errors
    env=env,
    text=True,               # Text mode (not binary)
    bufsize=1                # Line-buffered
)
```

**Message Format:**
```python
# Sending a request
msg = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
process.stdin.write(msg + "\n")  # MUST include newline
process.stdin.flush()

# Reading a response
response_line = process.stdout.readline()  # Blocks until newline received
response = json.loads(response_line.strip())
```

**Thread Safety:**
stdio communication uses locks to prevent concurrent writes (from `package_launcher.py:382-422`):

```python
def create_mcp_router(package_name: str, process: subprocess.Popen, 
                      process_lock: threading.Lock = None) -> APIRouter:
    if process_lock is None:
        process_lock = threading.Lock()
    
    @router.post(f"/{package_name}/mcp")
    async def proxy_jsonrpc(request: Dict[str, Any]):
        # Thread-safe communication with MCP server
        with process_lock:
            msg = json.dumps(request)
            process.stdin.write(msg + "\n")
            process.stdin.flush()
            response_line = process.stdout.readline()
        
        return JSONResponse(content=json.loads(response_line))
```

### 3.2 SSE (Server-Sent Events) Transport

**How it works:**
- MCP server runs its own HTTP server (e.g., on port 8000)
- JSON-RPC messages are sent via **HTTP POST** to `/messages/`
- Responses are returned as HTTP JSON responses
- FluidMCP still manages the process lifecycle

**Configuration:**
```json
{
  "mcpServers": {
    "game-hub": {
      "command": "uv",
      "args": ["--directory", "game-hub", "run", "server.py"],
      "env": {},
      "transport": "sse",
      "url": "http://127.0.0.1:8000"
    }
  }
}
```

**Implementation** (from `sse_handle.py:11-50`):

```python
class SseSubprocessHandle:
    """
    Wraps a subprocess.Popen for an SSE-transport MCP server.
    
    We still OWN the process (spawned via uv/python/etc.) so we keep the
    real Popen for lifecycle management (kill/terminate/poll).
    Communication happens over HTTP instead of stdin/stdout.
    """
    
    def __init__(self, process: subprocess.Popen, sse_url: str):
        self._process = process
        self.sse_url = sse_url
    
    def poll(self):
        return self._process.poll()
    
    def terminate(self):
        self._process.terminate()
    
    def kill(self):
        self._process.kill()
```

**HTTP Communication** (from `package_launcher.py:67-94`):

```python
async def _proxy_to_sse_server(sse_url: str, payload: dict, timeout: float = 60.0) -> dict:
    """
    Forward a JSON-RPC request to an SSE MCP server via POST /messages/.
    """
    import httpx
    
    messages_url = f"{sse_url.rstrip('/')}/messages/"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(messages_url, json=payload)
        resp.raise_for_status()
        return resp.json()
```

**When to Use SSE:**
- Server needs to manage its own HTTP endpoint
- Server requires WebSocket or SSE capabilities
- Server is written in a framework that prefers HTTP (e.g., FastAPI, Flask)
- Server needs to handle multiple concurrent connections independently

### 3.3 Protocol Comparison

| Feature | stdio Transport | SSE Transport |
|---------|----------------|---------------|
| **Communication** | stdin/stdout pipes | HTTP POST requests |
| **Process Management** | FluidMCP owns process | FluidMCP owns process |
| **Concurrency** | Lock-based serialization | HTTP connection pooling |
| **Latency** | Lower (no HTTP overhead) | Slightly higher (HTTP) |
| **Debugging** | Harder (binary pipes) | Easier (HTTP logs) |
| **Use Case** | Simple CLI tools | Web-based servers |
| **Default?** | ✅ Yes | ❌ No (opt-in) |

---

## 4. Tool Execution Flow

### 4.1 End-to-End Request Flow (stdio)

```
┌─────────────┐       ┌──────────────┐       ┌─────────────┐
│   Client    │       │   FluidMCP   │       │ MCP Server  │
│  (HTTP)     │       │   Gateway    │       │  (stdio)    │
└──────┬──────┘       └───────┬──────┘       └──────┬──────┘
       │                      │                      │
       │ 1. POST /{pkg}/mcp  │                      │
       │ tools/call request   │                      │
       ├─────────────────────>│                      │
       │                      │                      │
       │                      │ 2. Lock acquired     │
       │                      │    (thread-safe)     │
       │                      │                      │
       │                      │ 3. JSON-RPC to stdin │
       │                      ├─────────────────────>│
       │                      │                      │
       │                      │                      │ 4. Execute tool
       │                      │                      │    (blocking)
       │                      │                      │
       │                      │ 5. JSON-RPC response │
       │                      │<─────────────────────┤
       │                      │    via stdout        │
       │                      │                      │
       │                      │ 6. Lock released     │
       │                      │                      │
       │ 7. HTTP JSON response│                      │
       │<─────────────────────┤                      │
       │                      │                      │
```

### 4.2 Step-by-Step Execution

#### Step 1: Client Sends HTTP Request

```bash
curl -X POST http://localhost:8099/filesystem/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "read_file",
      "arguments": {
        "path": "/tmp/test.txt"
      }
    }
  }'
```

#### Step 2: FastAPI Router Receives Request

From `package_launcher.py:375-422`:

```python
@router.post(f"/{package_name}/mcp", tags=[package_name])
async def proxy_jsonrpc(
    http_request: Request,
    request: Dict[str, Any] = Body(...)
):
    collector = MetricsCollector(package_name)
    method = request.get("method", "unknown")
    
    # Track request with metrics
    with RequestTimer(collector, method):
        # Extract HTTP headers
        all_headers = dict(http_request.headers)
        
        # Inject headers into tools/call arguments
        if request.get("method") == "tools/call" and all_headers:
            params = request.get("params", {})
            if "arguments" not in params:
                params["arguments"] = {}
            params["arguments"]["headers"] = all_headers
            request["params"] = params
```

**Header Injection Feature:**
- HTTP headers from the client request are automatically injected into tool arguments
- Only applies to `tools/call` method
- Headers are added as `arguments.headers` in the MCP request
- Allows tools to access authentication tokens, user agents, etc.

#### Step 3: Thread-Safe Communication

From `package_launcher.py:390-422`:

```python
        # Thread-safe communication with MCP server
        with process_lock:
            msg = json.dumps(request)
            logger.debug(f"[{package_name}] Sending to MCP stdin: {msg[:200]}...")
            
            process.stdin.write(msg + "\n")
            process.stdin.flush()
            
            logger.debug(f"[{package_name}] Waiting for response from stdout...")
            response_line = process.stdout.readline()
            logger.debug(f"[{package_name}] Received from stdout: {response_line[:200]}...")
        
        return JSONResponse(content=json.loads(response_line))
```

**Thread Safety Guarantees:**
- Only one request can write to stdin at a time
- Ensures request/response ordering
- Prevents interleaved messages
- Lock is held for the entire request/response cycle

#### Step 4: MCP Server Processes Request

The MCP server (running in a separate process):
1. Reads JSON-RPC request from stdin (blocking readline)
2. Parses the request
3. Validates the tool name and arguments
4. Executes the tool implementation
5. Writes JSON-RPC response to stdout (one line)

#### Step 5: FluidMCP Returns HTTP Response

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "File contents here..."
      }
    ]
  }
}
```

### 4.3 Simplified REST Endpoints

FluidMCP provides **simplified REST endpoints** that wrap the JSON-RPC protocol (from `package_launcher.py:511-609`):

#### GET /{package}/mcp/tools/list

Pre-fills the JSON-RPC request:

```python
@router.get(f"/{package_name}/mcp/tools/list", tags=[package_name])
async def list_tools():
    request_payload = {
        "id": 1,
        "jsonrpc": "2.0",
        "method": "tools/list"
    }
    # ... send to MCP server via stdio
```

**Client usage:**
```bash
curl http://localhost:8099/filesystem/mcp/tools/list
```

#### POST /{package}/mcp/tools/call

Constructs full JSON-RPC request from simplified input:

```python
@router.post(f"/{package_name}/mcp/tools/call", tags=[package_name])
async def call_tool(request_body: Dict[str, Any]):
    params = request_body
    
    # Construct complete JSON-RPC request
    request_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": params
    }
    # ... send to MCP server
```

**Client usage:**
```bash
curl -X POST http://localhost:8099/filesystem/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "read_file",
    "arguments": {"path": "/tmp/test.txt"}
  }'
```

### 4.4 SSE Streaming Support

FluidMCP supports **Server-Sent Events (SSE)** for streaming responses (from `package_launcher.py:426-509`):

```python
@router.post(f"/{package_name}/sse", tags=[package_name])
async def sse_stream(request: Dict[str, Any]):
    async def event_generator() -> Iterator[str]:
        with process_lock:
            msg = json.dumps(request)
            process.stdin.write(msg + "\n")
            process.stdin.flush()
            
            # Stream responses line-by-line
            while True:
                response_line = process.stdout.readline()
                if not response_line:
                    break
                
                # Format as SSE event
                yield f"data: {response_line.strip()}\n\n"
                
                # Stop if final result received
                response_data = json.loads(response_line)
                if "result" in response_data:
                    break
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

**Use case:** Long-running operations that produce incremental results

---

## 5. Server Lifecycle Management

### 5.1 Server States

```
┌──────────┐   start    ┌──────────┐   stop     ┌──────────┐
│  Stopped │ ────────> │  Running │ ────────> │  Stopped │
└──────────┘            └──────────┘            └──────────┘
      ▲                      │                        │
      │                      │ error/crash            │
      │                      ▼                        │
      │                 ┌──────────┐   restart       │
      └─────────────── │  Failed  │ ────────────────┘
                        └──────────┘
```

### 5.2 Server Initialization Handshake

MCP servers require a **two-step initialization handshake** (from `package_launcher.py:261-359`):

```python
def initialize_mcp_server(process: subprocess.Popen, timeout: int = 30) -> bool:
    """
    Initialize MCP server with proper handshake.
    
    Returns:
        True if initialization successful
    """
    # Step 1: Check process is alive
    if process.poll() is not None:
        stderr_output = process.stderr.read()
        logger.error(f"Process died before initialization. stderr: {stderr_output}")
        return False
    
    # Step 2: Send initialize request
    init_request = {
        "jsonrpc": "2.0",
        "id": 0,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "roots": {"listChanged": True},
                "sampling": {}
            },
            "clientInfo": {
                "name": "fluidmcp-client",
                "version": "2.0.0"
            }
        }
    }
    
    process.stdin.write(json.dumps(init_request) + "\n")
    process.stdin.flush()
    
    # Step 3: Wait for initialize response
    start_time = time.time()
    while time.time() - start_time < timeout:
        if process.poll() is not None:
            logger.error(f"Process died during initialization")
            return False
        
        response_line = process.stdout.readline().strip()
        if response_line:
            try:
                response = json.loads(response_line)
                
                # Check if this is the initialize response
                if response.get("id") == 0 and "result" in response:
                    # Step 4: Send initialized notification
                    notif = {
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized"
                    }
                    process.stdin.write(json.dumps(notif) + "\n")
                    process.stdin.flush()
                    
                    logger.info("MCP server initialized successfully")
                    return True
            except json.JSONDecodeError:
                # Not JSON - likely a log message from the server
                # Some servers output logs to stdout instead of stderr
                continue
        
        time.sleep(0.1)
    
    logger.error(f"MCP initialization timeout after {timeout} seconds")
    return False
```

**Handshake Protocol:**
1. **Client → Server:** `initialize` request with protocol version and capabilities
2. **Server → Client:** `initialize` response with server info and capabilities
3. **Client → Server:** `notifications/initialized` notification (no response expected)
4. **Server:** Ready to accept `tools/list`, `tools/call`, etc.

**Error Handling:**
- Process dies → Immediate failure
- Timeout (30s default) → Failure with stderr logs
- Non-JSON output → Skipped (treated as server logs)
- Process spawned with `npx -y` → Longer timeout to allow package download

### 5.3 ServerManager Lifecycle

FluidMCP uses `ServerManager` for centralized process management (from `server_manager.py:1-100`):

```python
class ServerManager:
    """Manages MCP server processes and lifecycle."""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        
        # Process registry (in-memory)
        self.processes: Dict[str, subprocess.Popen] = {}
        self.configs: Dict[str, Dict[str, Any]] = {}
        self.start_times: Dict[str, float] = {}
        
        # Operation locks (prevent concurrent operations)
        self._operation_locks: Dict[str, asyncio.Lock] = {}
        
        # Health checker for process validation
        self.health_checker = HealthChecker()
        
        # Register cleanup handlers
        atexit.register(self._cleanup_on_exit)
```

**Key Features:**
- **In-memory process registry:** Fast lookups without database queries
- **Operation locks:** Prevent concurrent start/stop operations on same server
- **Automatic cleanup:** Graceful shutdown on process exit
- **State persistence:** Syncs process state to MongoDB
- **Health monitoring:** Periodic checks for crashed processes

### 5.4 Start Server Flow

From `server_manager.py:158-233`:

```python
async def start_server(self, id: str, config: Optional[Dict] = None, 
                      user_id: Optional[str] = None) -> bool:
    """
    Start an MCP server.
    
    Args:
        id: Unique server identifier
        config: Server configuration (if None, loads from database)
        user_id: User who is starting the server (for tracking)
    
    Returns:
        True if started successfully
    """
    # Acquire operation lock
    if id not in self._operation_locks:
        self._operation_locks[id] = asyncio.Lock()
    
    async with self._operation_locks[id]:
        # Check if already running
        if id in self.processes:
            process = self.processes[id]
            if process.poll() is None:
                logger.warning(f"Server '{id}' is already running")
                return False
        
        # Load config from database if not provided
        if config is None:
            config = await self.db.get_server_config(id)
            if not config:
                logger.error(f"No configuration found for server '{id}'")
                return False
        
        # Spawn the MCP process with timeout
        try:
            process = await asyncio.wait_for(
                self._spawn_mcp_process(id, config),
                timeout=30.0
            )
        except asyncio.TimeoutError:
            logger.error(f"Server startup timed out after 30 seconds")
            await self.db.save_instance_state({
                "server_id": id,
                "state": "failed",
                "last_error": "Server startup timed out"
            })
            return False
        
        if not process:
            return False
        
        # Store process and config
        self.processes[id] = process
        self.configs[id] = config
        self.start_times[id] = time.monotonic()
        
        # Update database state
        await self.db.save_instance_state({
            "server_id": id,
            "pid": process.pid,
            "state": "running",
            "started_at": datetime.now().isoformat()
        })
        
        return True
```

### 5.5 Stop Server Flow

From `server_manager.py:235-310`:

```python
async def stop_server(self, id: str, user_id: Optional[str] = None) -> bool:
    """
    Stop a running MCP server.
    
    Args:
        id: Server identifier
        user_id: User who is stopping the server
    
    Returns:
        True if stopped successfully
    """
    async with self._operation_locks.get(id, asyncio.Lock()):
        if id not in self.processes:
            logger.warning(f"Server '{id}' is not running")
            return False
        
        process = self.processes[id]
        
        try:
            # Try graceful termination first (SIGTERM)
            process.terminate()
            
            # Wait up to 5 seconds for graceful shutdown
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(process.wait),
                    timeout=5.0
                )
                logger.info(f"Server '{id}' terminated gracefully")
            except asyncio.TimeoutError:
                # Force kill if graceful shutdown failed
                logger.warning(f"Server '{id}' did not terminate, forcing kill...")
                process.kill()
                await asyncio.to_thread(process.wait)
                logger.info(f"Server '{id}' force killed")
            
            # Clean up registry
            del self.processes[id]
            if id in self.configs:
                del self.configs[id]
            if id in self.start_times:
                del self.start_times[id]
            
            # Update database state
            await self.db.save_instance_state({
                "server_id": id,
                "pid": None,
                "state": "stopped",
                "stopped_at": datetime.now().isoformat()
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Error stopping server '{id}': {e}")
            return False
```

**Graceful Shutdown Steps:**
1. Send SIGTERM signal (allows server to cleanup)
2. Wait up to 5 seconds for process exit
3. If still running, send SIGKILL (forceful)
4. Clean up process registry
5. Update database state to "stopped"

### 5.6 Restart Server Flow

From `server_manager.py:312-380`:

```python
async def restart_server(self, id: str, user_id: Optional[str] = None) -> bool:
    """
    Restart a running MCP server (stop then start).
    
    Args:
        id: Server identifier
        user_id: User performing the restart
    
    Returns:
        True if restarted successfully
    """
    async with self._operation_locks.get(id, asyncio.Lock()):
        name = id
        
        try:
            # Load config first
            config = await self.db.get_server_config(id)
            if not config:
                logger.error(f"No configuration found for server '{id}'")
                return False
            
            name = config.get("name", id)
            
            # Step 1: Stop if running
            if id in self.processes:
                process = self.processes[id]
                if process.poll() is None:
                    logger.info(f"Stopping server '{name}' for restart...")
                    
                    # Graceful termination
                    process.terminate()
                    try:
                        await asyncio.wait_for(
                            asyncio.to_thread(process.wait),
                            timeout=5.0
                        )
                    except asyncio.TimeoutError:
                        process.kill()
                        await asyncio.to_thread(process.wait)
                
                # Clean up
                del self.processes[id]
                if id in self.configs:
                    del self.configs[id]
                if id in self.start_times:
                    del self.start_times[id]
            
            # Step 2: Start with fresh process
            # Use _start_server_unlocked since we already hold the lock
            success = await self._start_server_unlocked(id, config, user_id)
            
            if success:
                logger.info(f"Server '{name}' restarted successfully")
            else:
                logger.error(f"Failed to restart server '{name}'")
            
            return success
            
        except Exception as e:
            logger.error(f"Error restarting server '{name}': {e}")
            return False
```

**Restart is atomic:**
- Single lock held for entire stop+start operation
- Prevents race conditions
- Ensures clean state transition
- Uses `_start_server_unlocked()` to avoid deadlock

### 5.7 Automatic Cleanup on Exit

From `server_manager.py:71-116`:

```python
def _cleanup_on_exit(self) -> None:
    """
    Cleanup handler called on process exit.
    Terminates all running MCP server processes.
    """
    if not self.processes:
        return
    
    logger.info(f"Cleaning up {len(self.processes)} running server(s)...")
    
    for server_id, process in list(self.processes.items()):
        try:
            if process.poll() is None:  # Process still running
                logger.info(f"Terminating server '{server_id}' (PID: {process.pid})")
                
                # Try graceful termination first
                process.terminate()
                
                # Wait up to 5 seconds
                try:
                    process.wait(timeout=5)
                    logger.info(f"Server '{server_id}' terminated gracefully")
                except subprocess.TimeoutExpired:
                    # Force kill
                    logger.warning(f"Forcing kill on '{server_id}'...")
                    process.kill()
                    process.wait(timeout=2)
                    logger.info(f"Server '{server_id}' force killed")
                
                # Reap zombie process
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
        
        except Exception as e:
            logger.error(f"Error cleaning up server '{server_id}': {e}")
    
    self.processes.clear()
    logger.info("All servers cleaned up")
```

**Cleanup features:**
- Registered with `atexit` module
- Runs on normal exit, Ctrl+C, or kill signal
- Prevents orphan processes
- Graceful termination with fallback to force kill

---

## 6. Error Handling

### 6.1 Initialization Errors

**Problem:** Server process dies during startup

**Detection:** `process.poll() is not None` in initialization loop

**Handling:**
```python
if process.poll() is not None:
    stderr_output = process.stderr.read()
    logger.error(f"Process died during initialization. stderr: {stderr_output}")
    return False
```

**Common causes:**
- Missing dependencies (e.g., API key not set)
- Invalid command or arguments
- Port already in use
- Permission errors

### 6.2 Environment Variable Placeholders

**Problem:** Config contains placeholder values like `<your-api-key>`

**Detection:** `is_placeholder()` utility function checks for placeholder patterns

**Handling** (from `package_launcher.py:176-199`):
```python
placeholders_found = []
for key, value in env_vars.items():
    if key not in env:  # Only add if not in shell env
        if is_placeholder(value):
            placeholders_found.append((key, value))
            logger.warning(
                f"Skipping placeholder value for {key}='{value}'. "
                f"Set this environment variable or use 'fmcp edit-env' to configure."
            )
        else:
            env[key] = value

if placeholders_found:
    logger.warning(
        f"Found {len(placeholders_found)} placeholder environment variable(s). "
        f"Server may fail to start. Use 'fmcp edit-env {pkg}' to configure: "
        f"{', '.join([k for k, v in placeholders_found])}"
    )
```

**User guidance:**
- Warning logged with specific variable names
- Suggestion to use `fmcp edit-env` command
- Server still attempts to start (may fail if required)

### 6.3 Communication Errors

**Problem:** Broken pipe (process died mid-request)

**Handling:**
```python
try:
    process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()
except (BrokenPipeError, OSError) as e:
    logger.error(f"Failed to write to stdin: {e}")
    return JSONResponse(
        status_code=500,
        content={"error": f"Process pipe broken: {str(e)}"}
    )
```

**Problem:** Process doesn't respond / timeout

**Handling:** Timeout configured at 60 seconds for regular requests:
```python
response_line = await asyncio.wait_for(
    asyncio.to_thread(process.stdout.readline),
    timeout=60.0
)
```

### 6.4 Non-JSON Output

**Problem:** Server outputs logs to stdout instead of stderr

**Handling:** Skip non-JSON lines during initialization:
```python
try:
    response = json.loads(response_line)
    # Process JSON response
except json.JSONDecodeError:
    # Not JSON - likely a log message
    non_json_lines.append(response_line[:200])
    logger.debug(f"Skipping non-JSON line: {response_line[:200]}")
    continue
```

**Result:** Initialization continues, logs are ignored

### 6.5 SSE Server Connection Errors

**Problem:** SSE server not reachable

**Handling** (from `package_launcher.py:67-94`):
```python
try:
    resp = await client.post(messages_url, json=payload)
    resp.raise_for_status()
    return resp.json()
except httpx.HTTPStatusError as e:
    raise HTTPException(
        e.response.status_code,
        f"SSE server returned HTTP {e.response.status_code}"
    )
except httpx.ConnectError:
    raise HTTPException(
        503,
        f"Cannot reach SSE server at {sse_url}. Is it still running?"
    )
except Exception as e:
    logger.error(f"SSE proxy error → {messages_url}: {e}")
    raise HTTPException(500, f"SSE proxy error: {str(e)}")
```

### 6.6 Metrics and Monitoring

FluidMCP tracks errors via `MetricsCollector` (from `package_launcher.py:377-384`):

```python
collector = MetricsCollector(package_name)

with RequestTimer(collector, method):
    try:
        # ... request handling
    except Exception as e:
        collector.record_error("io_error")  # Track error
        logger.error(f"Error in proxy: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})
```

**Error categories:**
- `io_error` - Communication failures
- `startup_timeout` - Server failed to start in time
- `broken_pipe` - Process died mid-request
- `json_decode_error` - Invalid response format

### 6.7 Security Error Handling

**Problem:** Invalid or missing bearer token in secure mode

**Handling** (from `package_launcher.py:97-106`):
```python
def get_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate bearer token if secure mode is enabled"""
    bearer_token = os.environ.get("FMCP_BEARER_TOKEN")
    secure_mode = os.environ.get("FMCP_SECURE_MODE") == "true"
    
    if not secure_mode:
        return None
    
    if not credentials or credentials.scheme.lower() != "bearer" \
       or credentials.credentials != bearer_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing authorization token"
        )
    return credentials.credentials
```

**Result:** 401 Unauthorized response, request rejected

---

## Summary

### Key Takeaways

1. **MCP Server Definition:**
   - Implements JSON-RPC 2.0 with MCP protocol version `2024-11-05`
   - Supports stdio or SSE transport
   - Defined via metadata.json with three input formats

2. **Tool Discovery:**
   - Discovered via `tools/list` method during initialization
   - Cached in database for fast access
   - JSON Schema defines input parameters

3. **Communication Protocol:**
   - **stdio (default):** JSON-RPC over stdin/stdout pipes, line-buffered
   - **SSE (opt-in):** JSON-RPC over HTTP POST /messages/
   - Thread-safe with locks for concurrent requests

4. **Execution Flow:**
   - Client → FastAPI → stdio/HTTP → MCP Server → Response
   - Headers auto-injected into tools/call arguments
   - Simplified REST endpoints wrap JSON-RPC

5. **Lifecycle Management:**
   - Two-step initialization handshake (initialize + initialized)
   - Graceful shutdown with SIGTERM, fallback to SIGKILL
   - Automatic cleanup on process exit
   - Operation locks prevent race conditions

6. **Error Handling:**
   - Placeholder environment variables skipped with warnings
   - Broken pipes detected and logged
   - Non-JSON output ignored during initialization
   - Comprehensive metrics tracking

### Implementation Files

- **package_launcher.py** (600 lines): FastAPI routing, stdio communication, tool endpoints
- **server_manager.py** (1000+ lines): Process lifecycle, state management, health monitoring
- **config_resolver.py**: Unified config resolution from multiple sources
- **sse_handle.py**: SSE transport wrapper for HTTP-based MCP servers
- **server_builder.py**: Config normalization and ID generation
- **metadata-schema.md**: Complete metadata structure documentation

---

**Document Version:** 1.0  
**Last Updated:** 2026-03-24  
**FluidMCP Version:** 2.0.0+
