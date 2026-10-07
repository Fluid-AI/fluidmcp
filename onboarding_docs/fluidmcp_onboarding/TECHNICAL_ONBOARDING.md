# FluidMCP - Technical Onboarding Guide

**Version:** 1.0  
**Last Updated:** March 24, 2026  
**Target Audience:** New developers joining the FluidMCP project

---

## Table of Contents

1. [Overview](#1-overview)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Backend (Gateway)](#3-backend-gateway)
4. [MCP Server Model](#4-mcp-server-model)
5. [Frontend](#5-frontend)
6. [End-to-End Flow](#6-end-to-end-flow)
7. [Key Features](#7-key-features)
8. [Important Files and Folders](#8-important-files-and-folders)
9. [Developer Workflow](#9-developer-workflow)

---

## 1. Overview

**FluidMCP** is a CLI tool and API gateway for orchestrating multiple Model Context Protocol (MCP) servers through a unified interface. It enables:

- **Running multiple MCP servers** from a single configuration
- **Unified FastAPI gateway** exposing all servers via HTTP/REST
- **LLM inference** through local (vLLM, Ollama) or cloud (Replicate) providers
- **Dynamic server management** with MongoDB persistence
- **Web UI** for server monitoring, tool execution, and chat

### What Problem Does It Solve?

MCP servers typically run as isolated processes communicating over stdio (standard input/output). FluidMCP:
1. **Orchestrates** multiple MCP servers simultaneously
2. **Exposes** them via REST APIs with automatic route generation
3. **Manages** their lifecycle (start/stop/restart)
4. **Provides** a unified web interface for interaction
5. **Integrates** LLM inference with tool execution

---

## 2. High-Level Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (React SPA)                     │
│  Dashboard │ Tool Runner │ LLM Playground │ Server Manager  │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP/REST API
                           ▼
┌─────────────────────────────────────────────────────────────┐
│               FastAPI Gateway (Port 8099)                    │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Management API: /api/servers, /api/models             │ │
│  │  LLM Proxy: /api/llm/v1/chat/completions              │ │
│  │  Dynamic MCP Routes: /{server_id}/mcp/tools/*         │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────┬─────────────────────┬─────────────────┬──────────┘
           │                     │                 │
           ▼                     ▼                 ▼
┌──────────────────┐  ┌──────────────────┐  ┌────────────────┐
│  MCP Server 1    │  │  MCP Server 2    │  │  LLM Models    │
│  (subprocess)    │  │  (subprocess)    │  │  (vLLM/Ollama) │
│  stdio pipes     │  │  stdio pipes     │  │  HTTP          │
└──────────────────┘  └──────────────────┘  └────────────────┘
           │                     │                 │
           └─────────────────────┴─────────────────┘
                           │
                           ▼
                   ┌──────────────────┐
                   │  MongoDB         │
                   │  (Persistence)   │
                   └──────────────────┘
```

### How Components Interact

1. **Frontend** → Sends HTTP requests to FastAPI Gateway
2. **Gateway** → Routes requests to appropriate MCP server or LLM model
3. **MCP Servers** → Run as subprocesses, communicate via JSON-RPC over stdio
4. **LLM Models** → Communicate via HTTP (OpenAI-compatible endpoints)
5. **MongoDB** → Stores server configs, model configs, and runtime state

### Key Design Decisions

- **One subprocess per MCP server** - Process isolation for stability
- **Thread locks per server** - Prevents concurrent stdio access
- **Dynamic routing** - Routes created at runtime as servers start
- **HTTP-first** - All interactions via REST APIs (no direct CLI usage in production)
- **OpenAI compatibility** - Standard `/v1/chat/completions` endpoint

---

## 3. Backend (Gateway)

### 3.1 Entry Points

The backend has multiple entry points depending on usage mode:

| File | Purpose | Command |
|------|---------|---------|
| [fluidmcp/cli/__init__.py](fluidmcp/cli/__init__.py) | Package-level entry point | `import fluidmcp.cli` |
| [fluidmcp/cli/__main__.py](fluidmcp/cli/__main__.py) | Module execution handler | `python -m fluidmcp.cli` |
| [fluidmcp/cli/cli.py](fluidmcp/cli/cli.py) | Core CLI with argparse | `fluidmcp <command>` |
| [fluidmcp/cli/server.py](fluidmcp/cli/server.py) | FastAPI server entry | `fmcp serve` |

**Aliases:** `fluidmcp`, `fmcp`, `fluidai-mcp` (all equivalent)

### 3.2 Startup Flow

#### Production Mode: `fmcp serve` (Recommended)

```
┌──────────────────────────────────────────────────────────────┐
│ 1. CLI Parse (cli.py)                                        │
│    - Parse "serve" command with --port, --require-persistence│
└──────────────────────┬───────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. Persistence Setup (server.py)                             │
│    - Connect to MongoDB: DatabaseManager.init_db()          │
│    - Retry: 3 attempts with exponential backoff (2s→4s→8s)  │
│    - Fallback: InMemoryBackend if MongoDB unavailable       │
└──────────────────────┬───────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. Server Manager Init (server_manager.py)                   │
│    - Initialize ServerManager with persistence backend      │
│    - Load existing server configs from DB                   │
└──────────────────────┬───────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ 4. FastAPI App Creation (server.py::create_app)             │
│    - CORS middleware (secure by default)                    │
│    - Request size limiting (10MB default)                   │
│    - Management API routes (/api/servers, /api/models)      │
│    - Dynamic MCP router (empty initially)                   │
│    - Frontend routes (React SPA)                            │
│    - Health endpoint (/health)                              │
│    - Metrics endpoint (/metrics)                            │
└──────────────────────┬───────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ 5. Model & Server Restore                                    │
│    - Load LLM models from DB: load_models_from_persistence()│
│    - Start background tasks (idle cleanup, health checks)   │
└──────────────────────┬───────────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────────┐
│ 6. Uvicorn Launch                                            │
│    - Start server on configured port (default: 8099)        │
│    - Listen for HTTP requests                               │
└──────────────────────────────────────────────────────────────┘
```

**Key Characteristics:**
- Persistent API server (doesn't block terminal)
- Dynamic server management via REST API
- MongoDB for configuration persistence
- Survives restarts (configs reloaded from DB)

#### Legacy Mode: `fmcp run` (Deprecated)

```
CLI Parse → Config Resolve → Launch All Servers → 
Create FastAPI App → Start Uvicorn (blocks terminal)
```

**Key Characteristics:**
- Immediate server launch
- Configuration from file, S3, or installed packages
- Blocks terminal until stopped
- No persistence

### 3.3 Server Discovery, Installation, and Startup

#### Configuration Sources

FluidMCP supports **5 configuration sources** ([config_resolver.py](fluidmcp/cli/services/config_resolver.py)):

| Source | Example | Resolution |
|--------|---------|------------|
| **Package String** | `Author/Package@1.0` | Resolves from `.fmcp-packages/Author/Package/1.0/` |
| **All Installed** | `fmcp run all` | Scans `.fmcp-packages/` for all metadata.json |
| **Local File** | `fmcp run config.json --file` | Reads JSON, supports 3 sub-formats |
| **S3 URL** | `fmcp run s3://... --s3` | Downloads config from presigned URL |
| **GitHub Repo** | `fmcp github owner/repo` | Clones repo, extracts/creates metadata |

#### Configuration Formats

**Format 1: Direct Server Config** (No installation required)
```json
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
      "env": {"VAR": "value"}
    }
  }
}
```
- Runs immediately
- FluidMCP creates temp metadata in `.fmcp-packages/.temp_servers/`

**Format 2: GitHub Repository**
```json
{
  "mcpServers": {
    "my-server": {
      "github_repo": "owner/repo",
      "branch": "main",
      "github_token": "ghp_...",
      "env": {"API_KEY": "value"}
    }
  }
}
```
- Clones to `.fmcp-packages/owner/repo/branch/`
- Extracts metadata from README.md if metadata.json absent
- Working directory set intelligently based on command type

**Format 3: Package String** (Requires registry)
```json
{
  "mcpServers": {
    "my-server": "Author/Package@1.0"
  }
}
```
- Downloads from FluidMCP registry
- Installs to `.fmcp-packages/Author/Package/1.0/`

#### Installation Flow

**Command:** `fmcp install Author/Package@1.0`

```python
# package_installer.py::install_package()
1. POST to registry: MCP_FETCH_URL with MCP_TOKEN
2. Download package tarball
3. Extract to: ~/.fluidmcp/packages/Author/Package/1.0/
4. Validate metadata.json exists
5. Save to master config (if --master flag)
```

#### Server Launch Flow

**Key File:** [package_launcher.py](fluidmcp/cli/services/package_launcher.py)

```python
# 1. Launch subprocess
def launch_mcp_using_fastapi_proxy(dest_dir):
    # Read metadata.json
    metadata = json.load(open(f"{dest_dir}/metadata.json"))
    
    # Resolve command (find npm/npx paths)
    command = resolve_command_path(metadata["command"])
    
    # Replace placeholders: <path to mcp-servers>
    args = [arg.replace("<path to mcp-servers>", dest_dir) 
            for arg in metadata["args"]]
    
    # Spawn subprocess with stdio pipes
    process = subprocess.Popen(
        [command] + args,
        stdin=PIPE, stdout=PIPE, stderr=PIPE,
        env=env, cwd=working_dir
    )
    
    # 2. Initialize (JSON-RPC handshake)
    initialize_mcp_server(process, timeout=30)
    
    # 3. Create FastAPI router
    router = create_mcp_router(package_name, process)
    
    return (package_name, router, process)
```

#### Initialization Handshake

MCP servers follow a **3-step handshake** (JSON-RPC 2.0):

```
Client (FluidMCP)              Server (MCP Process)
       │                              │
       ├─── initialize Request ───────▶
       │    {"jsonrpc": "2.0",        │
       │     "method": "initialize",  │
       │     "params": {               │
       │       "protocolVersion": "2024-11-05",
       │       "capabilities": {},     │
       │       "clientInfo": {...}     │
       │     }                          │
       │    }                          │
       │                              │
       ◀── initialize Response ─────┤
       │    {"result": {               │
       │       "protocolVersion": "...",
       │       "capabilities": {...},  │
       │       "serverInfo": {...}     │
       │     }                          │
       │    }                          │
       │                              │
       ├─ initialized Notification ───▶
       │    {"jsonrpc": "2.0",        │
       │     "method": "notifications/initialized"}
       │                              │
       └───── Server Ready ──────────┘
```

After this handshake, the server is ready to receive `tools/list` and `tools/call` requests.

### 3.4 Port Configuration

**Default Ports:**

```bash
MCP_CLIENT_SERVER_PORT=8090        # Single package mode (legacy)
MCP_CLIENT_SERVER_ALL_PORT=8099    # Unified gateway (production)
```

**Port Selection Logic:**
- `fmcp run author/package` → 8090 (single server)
- `fmcp run all` → 8099 (all servers)
- `fmcp serve` → 8099 (configurable via `--port`)

**Port Management** ([network_utils.py](fluidmcp/cli/services/network_utils.py)):
- `is_port_in_use()` - Checks availability with socket binding
- `kill_process_on_port()` - Force-kills process (used with `--force-reload`)
- `find_free_port(start, end)` - Finds available port in range
- `MCP_PORT_RELEASE_TIMEOUT=5` - Seconds to wait for port release

### 3.5 API Structure

FluidMCP exposes a comprehensive REST API:

#### Management API

**Base:** `/api`

**Server Management:**
```
POST   /api/servers              # Add server configuration
GET    /api/servers              # List all servers (with filters)
GET    /api/servers/{id}         # Get server details
PUT    /api/servers/{id}         # Update server configuration
DELETE /api/servers/{id}         # Remove server
POST   /api/servers/{id}/start   # Start server process
POST   /api/servers/{id}/stop    # Stop server process
POST   /api/servers/{id}/restart # Restart server
GET    /api/servers/{id}/logs    # Tail server logs
GET    /api/servers/{id}/status  # Get runtime status
```

**LLM Model Management:**
```
POST   /api/models/register      # Register LLM model (vLLM/Replicate/Ollama)
GET    /api/models               # List all models
GET    /api/models/{id}          # Get model details
PUT    /api/models/{id}          # Update model config
DELETE /api/models/{id}          # Delete model
POST   /api/models/{id}/rollback # Rollback to previous version
```

**LLM Inference (OpenAI-Compatible):**
```
POST   /api/llm/v1/chat/completions    # Chat completions (unified)
POST   /api/llm/v1/completions         # Text completions
GET    /api/llm/v1/models              # List available models
```

**Multimodal (vLLM Omni):**
```
POST   /api/llm/v1/generate/image      # Text-to-image
POST   /api/llm/v1/generate/video      # Text-to-video  
POST   /api/llm/v1/animate             # Image-to-video
GET    /api/llm/predictions/{id}       # Check generation status
```

#### Dynamic MCP Routes

Created automatically when each MCP server starts:

```
POST   /{server_id}/mcp               # JSON-RPC proxy (generic)
POST   /{server_id}/sse               # Server-Sent Events streaming
GET    /{server_id}/mcp/tools/list    # List available tools
POST   /{server_id}/mcp/tools/call    # Execute specific tool
```

Example: If you start a server with ID `filesystem`, you get:
- `POST /filesystem/mcp/tools/list`
- `POST /filesystem/mcp/tools/call`

#### System Endpoints

```
GET    /                         # API info
GET    /health                   # Health check (includes DB status)
GET    /metrics                  # Prometheus metrics
GET    /docs                     # Swagger UI
```

### 3.6 Tool Execution Flow (Internal)

When a user clicks "Execute" on a tool in the UI:

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: HTTP Request Arrives                                 │
│ POST /filesystem/mcp/tools/call                             │
│ Body: {"name": "read_file", "arguments": {"path": "/tmp/test.txt"}}
└────────────────────────┬─────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 2: FastAPI Router Handler (package_launcher.py)        │
│ - Extract tool name and arguments                           │
│ - Inject HTTP headers into arguments.headers                │
│ - Build JSON-RPC request:                                   │
│   {                                                          │
│     "jsonrpc": "2.0",                                       │
│     "id": 2,                                                │
│     "method": "tools/call",                                 │
│     "params": {                                             │
│       "name": "read_file",                                  │
│       "arguments": {                                        │
│         "path": "/tmp/test.txt",                           │
│         "headers": {...}  ← Auto-injected                  │
│       }                                                     │
│     }                                                       │
│   }                                                         │
└────────────────────────┬─────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 3: Thread-Safe Subprocess Communication                │
│ with process_lock:  # Prevents race conditions              │
│     process.stdin.write(msg + "\n")                         │
│     process.stdin.flush()                                   │
│     response_line = process.stdout.readline()               │
└────────────────────────┬─────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 4: MCP Server Processes Request                        │
│ - Reads JSON-RPC from stdin                                 │
│ - Executes tool logic                                       │
│ - Writes JSON-RPC response to stdout                        │
└────────────────────────┬─────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ Step 5: Response Parsing & Metrics                          │
│ - Parse JSON from stdout                                    │
│ - Record metrics (latency, success/error)                   │
│ - Return HTTP response to client                            │
└─────────────────────────────────────────────────────────────┘
```

**Critical Implementation Details:**

1. **Thread Safety:** Each server has a dedicated `threading.Lock` stored in `_process_locks` dictionary
2. **Header Injection:** HTTP headers automatically injected into tool arguments for authentication/context
3. **Metrics Collection:** Every tool call is timed and logged to Prometheus
4. **Error Handling:** Broken pipe detection, JSON decode errors, timeout protection

### 3.7 Key Service Files

| File | Responsibility |
|------|----------------|
| [config_resolver.py](fluidmcp/cli/services/config_resolver.py) | Resolves configuration from 5 sources, normalizes formats |
| [package_installer.py](fluidmcp/cli/services/package_installer.py) | Downloads packages from registry, extracts to `.fmcp-packages/` |
| [package_launcher.py](fluidmcp/cli/services/package_launcher.py) | Spawns MCP server subprocesses, creates FastAPI routers |
| [run_servers.py](fluidmcp/cli/services/run_servers.py) | Unified server launcher, assembles FastAPI app |
| [server_manager.py](fluidmcp/cli/services/server_manager.py) | Dynamic server lifecycle (start/stop/restart), log management |
| [llm_launcher.py](fluidmcp/cli/services/llm_launcher.py) | vLLM/Ollama process management, health monitoring, auto-restart |
| [replicate_client.py](fluidmcp/cli/services/replicate_client.py) | Replicate API client, polling-based predictions |
| [github_utils.py](fluidmcp/cli/services/github_utils.py) | Repository cloning, metadata extraction from README |
| [metrics.py](fluidmcp/cli/services/metrics.py) | Prometheus metrics (requests, latency, errors, uptime) |
| [network_utils.py](fluidmcp/cli/services/network_utils.py) | Port management, process killing |
| [auth.py](fluidmcp/cli/auth.py) | Bearer token validation, secure mode enforcement |

---

## 4. MCP Server Model

### 4.1 What Defines an MCP Server?

An MCP server is a **JSON-RPC 2.0 process** that implements the Model Context Protocol specification (version `2024-11-05`). It must:

1. **Communicate** via stdin/stdout (or optionally SSE)
2. **Implement** initialization handshake (`initialize` method)
3. **Expose** tools via `tools/list` method
4. **Execute** tools via `tools/call` method
5. **Follow** JSON-RPC 2.0 message format

### 4.2 Metadata Structure

Every MCP server needs a `metadata.json` file:

```json
{
  "author": "AuthorName",
  "package": "package-name",
  "version": "1.0.0",
  "category": "filesystem",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
  "env": {
    "API_KEY": "${API_KEY}"
  },
  "description": "Provides filesystem access tools",
  "dependencies": {
    "npm": "@modelcontextprotocol/server-filesystem@latest"
  }
}
```

**Key Fields:**
- `command` - Executable to run (e.g., `npx`, `python`, `node`)
- `args` - Command-line arguments
- `env` - Environment variables (supports placeholders like `${VAR}`)
- `dependencies` - External dependencies (npm, pip, etc.)

### 4.3 Tool Definition

Tools are defined using **JSON Schema** with three required properties:

```json
{
  "name": "read_file",
  "description": "Read the contents of a file from the filesystem",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Absolute path to the file"
      }
    },
    "required": ["path"]
  }
}
```

**Discovery:** Tools are discovered by sending `tools/list` JSON-RPC request during initialization. The response is **cached in MongoDB** for fast access.

**Supported Schema Types:**
- `string`, `number`, `boolean`, `array`, `object`
- Enums via `enum` keyword
- Nested objects and arrays
- Optional vs required fields

### 4.4 Communication Mechanism

FluidMCP supports **two transport mechanisms**:

#### stdio (Default - Recommended)

**Advantages:**
- Lower latency (no HTTP overhead)
- Simpler debugging (can test with console I/O)
- Built-in process isolation

**How It Works:**
```python
# Write request to stdin (line-buffered)
msg = json.dumps(request_payload)
process.stdin.write(msg + "\n")
process.stdin.flush()

# Read response from stdout (line-buffered)
response_line = process.stdout.readline()
response_data = json.loads(response_line)
```

**Thread Safety:** Each server has a `threading.Lock` to prevent concurrent stdin/stdout access

#### SSE (Optional)

**When to Use:**
- Server already runs as HTTP service
- Long-running operations need progress updates
- Slightly higher latency is acceptable

**How It Works:**
```python
# FluidMCP still manages process lifecycle
# But communication goes via HTTP POST to server's /messages/ endpoint
POST http://localhost:{server_port}/messages/
Body: {"jsonrpc": "2.0", "method": "tools/call", ...}
```

### 4.5 Tool Execution Protocol

**Request Format:**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "read_file",
    "arguments": {
      "path": "/tmp/test.txt",
      "headers": {
        "authorization": "Bearer ...",
        "user-agent": "..."
      }
    }
  }
}
```

**Response Format (Success):**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
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

**Response Format (Error):**
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "error": {
    "code": -32603,
    "message": "File not found",
    "data": {}
  }
}
```

**Content Types:**
- `text` - Plain text response
- `image` - Base64-encoded image data
- `resource` - Resource URI with metadata

### 4.6 Server Lifecycle

**States:**
- `not_running` - Server not started
- `starting` - Initialization in progress
- `running` - Ready to accept requests
- `stopping` - Graceful shutdown in progress
- `stopped` - Process terminated
- `error` - Failed to start or crashed

**Lifecycle Operations:**

**Start:**
```python
# server_manager.py::start_server()
1. Validate config in database
2. Check if already running (prevent duplicates)
3. Spawn subprocess with launch_mcp_using_fastapi_proxy()
4. Perform initialization handshake (30s timeout)
5. Fetch tools with tools/list request
6. Cache tools in database
7. Add router to FastAPI app
8. Update status to "running"
```

**Stop:**
```python
# server_manager.py::stop_server()
1. Send SIGTERM to process
2. Wait 5 seconds for graceful shutdown
3. Send SIGKILL if still running
4. Remove router from FastAPI
5. Clean up resources
6. Update status to "stopped"
```

**Restart:**
```python
# server_manager.py::restart_server()
1. Stop server (if running)
2. Wait for process cleanup
3. Start server with same config
```

---

## 5. Frontend

### 5.1 Technology Stack

**Core:**
- **React 19.2.0** - UI framework
- **TypeScript 5.9.3** - Type safety
- **Vite** - Build tool and dev server
- **React Router DOM 7.11.0** - Client-side routing

**UI Libraries:**
- **Tailwind CSS 3.4.19** - Utility-first styling
- **Radix UI** - Accessible component primitives (28 components)
- **Lucide React** - Icon library
- **shadcn/ui** - Pre-styled components built on Radix

**State Management:**
- **Custom hooks** - No Redux/Zustand
- **Local component state** with `useState`
- **14 custom hooks** for API interactions

**Form Management:**
- **React Hook Form 7.71.1** - Form state management
- **Zod 3.25.76** - Schema validation

### 5.2 Main Pages and Features

The frontend has **9 primary routes**:

| Page | Route | Purpose |
|------|-------|---------|
| **Dashboard** | `/` or `/servers` | View all MCP servers with status cards, filtering, search, pagination |
| **Status** | `/status` | Monitor active servers, quick stop/restart actions |
| **ServerDetails** | `/servers/:serverId` | Detailed server view: tools list, logs, environment variables |
| **ToolRunner** | `/servers/:serverId/tools/:toolName` | Execute MCP tools with dynamic JSON Schema forms |
| **ManageServers** | `/servers/manage` | CRUD operations for server configurations |
| **LLMModels** | `/llm/models` | List and manage LLM models (vLLM, Ollama, Replicate) |
| **LLMModelDetails** | `/llm/models/:modelId` | Detailed model view: health status, logs, metrics |
| **LLMPlayground** | `/llm/playground` | Interactive chat interface for testing LLM models |
| **Documentation** | `/documentation` | Usage guides and API documentation |

### 5.3 Component Structure

```
frontend/src/
├── pages/              # Route-level components (9 pages)
│   ├── Dashboard.tsx         # Server overview cards
│   ├── Status.tsx            # Active servers monitoring
│   ├── ServerDetails.tsx     # Single server details
│   ├── ToolRunner.tsx        # Tool execution interface
│   ├── ManageServers.tsx     # Server CRUD operations
│   ├── LLMModels.tsx         # LLM model list
│   ├── LLMModelDetails.tsx   # Single model details
│   ├── LLMPlayground.tsx     # Chat interface
│   └── Documentation.tsx     # API documentation
│
├── components/         # Reusable UI components
│   ├── ui/            # shadcn/ui primitives (Button, Dialog, etc.)
│   ├── form/          # Dynamic JSON Schema forms
│   │   └── JsonSchemaForm.tsx  # Auto-generates forms from tool schemas
│   ├── result/        # Tool execution result viewers
│   │   └── ToolResult.tsx      # Multi-format result renderer
│   ├── ServerCard.tsx           # Server status cards
│   ├── LLMModelCard.tsx         # LLM model cards
│   ├── Navbar.tsx               # Navigation header
│   └── Footer.tsx               # Footer
│
├── hooks/             # Custom React hooks (14 hooks)
│   ├── useServers.ts           # Server list & lifecycle
│   ├── useServerDetails.ts     # Single server data
│   ├── useServerManagement.ts  # Server CRUD operations
│   ├── useLLMModels.ts         # LLM model list & management
│   ├── useToolRunner.ts        # Tool execution & history
│   ├── usePolling.ts           # Generic polling utility
│   └── useDebounce.ts          # Debounced search
│
├── services/          # API client and utilities
│   ├── api.ts                  # Typed API client (singleton)
│   ├── toolHistory.ts          # localStorage-based tool history
│   └── toast.ts                # Toast notification helpers
│
└── types/            # TypeScript type definitions
    ├── server.ts              # Server, Tool, Environment types
    └── llm.ts                 # LLM model, Chat types
```

### 5.4 State Management Approach

FluidMCP uses **custom hooks** as the state management layer (no global state library):

**Example: `useServers` Hook**

```typescript
// hooks/useServers.ts
export const useServers = () => {
  const [servers, setServers] = useState<Server[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Fetch servers
  const fetchServers = async () => {
    const data = await apiClient.listServers();
    setServers(data.servers);
  };

  // Start server
  const startServer = async (serverId: string) => {
    await apiClient.startServer(serverId);
    await fetchServers(); // Refresh list
  };

  // Stop server
  const stopServer = async (serverId: string) => {
    await apiClient.stopServer(serverId);
    await fetchServers();
  };

  return { servers, loading, error, startServer, stopServer, refetch: fetchServers };
};
```

**Key Patterns:**
- **AbortController** for request cancellation
- **Mounted refs** to prevent state updates after unmount
- **useCallback** to memoize callbacks
- **useMemo** for expensive computations
- **Functional setState** to avoid race conditions

### 5.5 Backend Communication

**API Client:** [services/api.ts](fluidmcp/frontend/src/services/api.ts)

```typescript
class ApiClient {
  private baseUrl: string;

  constructor() {
    // Use env var or current origin
    this.baseUrl = import.meta.env.VITE_API_BASE_URL || window.location.origin;
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    // Add timeout (30s default, 120s for GitHub operations)
    // Add AbortController support
    // Parse JSON response
    // Throw ApiHttpError on failure
  }

  // Typed methods for all endpoints:
  listServers(options?: {...}): Promise<ServersListResponse>
  startServer(serverId: string): Promise<ServerStartResponse>
  runTool(serverId: string, toolName: string, params: {...}): Promise<ToolExecutionResponse>
  chatCompletion(payload: ChatCompletionRequest): Promise<ChatCompletionResponse>
  // ... 30+ more methods
}

// Singleton instance
export default new ApiClient();
```

**Error Handling:**
```typescript
export class ApiHttpError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}
```

**Request Features:**
- Automatic timeout (configurable per request)
- AbortController integration for cancellation
- Typed responses with TypeScript interfaces
- Centralized error handling

---

## 6. End-to-End Flow

### Complete User Journey: Execute a Tool

```
┌─────────────────────────────────────────────────────────────┐
│ USER ACTION: Click "Execute read_file" in UI                │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND (React)                                             │
│ 1. User fills form in ToolRunner.tsx                        │
│    - JsonSchemaForm auto-generated from tool schema         │
│    - Input: {"path": "/tmp/test.txt"}                      │
│ 2. handleExecute() called                                   │
│    - Validates form with React Hook Form + Zod              │
│    - Calls apiClient.runTool(serverId, toolName, params)    │
└──────────────────────────┬──────────────────────────────────┘
                           ▼ HTTP POST
┌─────────────────────────────────────────────────────────────┐
│ GATEWAY (FastAPI)                                            │
│ 3. Request hits: POST /filesystem/mcp/tools/call           │
│    - Bearer token validated (if secure mode)                │
│    - Rate limiting checked (if Redis enabled)               │
│ 4. Router handler in package_launcher.py                    │
│    - Inject HTTP headers into arguments                     │
│    - Build JSON-RPC request                                 │
│    - Acquire process lock                                   │
│    - Start metrics timer                                    │
└──────────────────────────┬──────────────────────────────────┘
                           ▼ JSON-RPC over stdin
┌─────────────────────────────────────────────────────────────┐
│ MCP SERVER (Subprocess)                                      │
│ 5. Server reads from stdin                                  │
│    - Parses JSON-RPC request                                │
│    - Validates tool name and arguments                      │
│ 6. Executes tool logic                                      │
│    - In this case: fs.readFileSync("/tmp/test.txt")        │
│ 7. Writes response to stdout                                │
│    - Serializes result as JSON-RPC response                 │
└──────────────────────────┬──────────────────────────────────┘
                           ▼ JSON-RPC response
┌─────────────────────────────────────────────────────────────┐
│ GATEWAY (FastAPI)                                            │
│ 8. Read response from stdout                                │
│    - Parse JSON                                             │
│    - Release process lock                                   │
│    - Record metrics (latency, success/error)                │
│    - Return HTTP response                                   │
└──────────────────────────┬──────────────────────────────────┘
                           ▼ HTTP 200 OK
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND (React)                                             │
│ 9. ToolRunner receives response                             │
│    - Store in execution history (localStorage)              │
│    - Render with ToolResult.tsx                             │
│      - Auto-detects format: JSON/Table/Text/MCP Content     │
│    - Display execution time                                 │
│    - Show success/error toast                               │
└─────────────────────────────────────────────────────────────┘
```

**Timing:**
- UI → Gateway: ~50ms (network)
- Gateway → MCP Server: ~5-100ms (tool execution)
- Total: ~100-200ms for simple tools

### Complete User Journey: Chat with LLM

```
┌─────────────────────────────────────────────────────────────┐
│ USER ACTION: Send message "What is 2+2?" in LLM Playground  │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND (LLMPlayground.tsx)                                │
│ 1. handleSend() called                                      │
│    - Add user message to state                              │
│    - Create AbortController for cancellation                │
│    - Call apiClient.chatCompletion()                        │
└──────────────────────────┬──────────────────────────────────┘
                           ▼ HTTP POST
┌─────────────────────────────────────────────────────────────┐
│ GATEWAY (FastAPI)                                            │
│ 2. Request hits: POST /api/llm/v1/chat/completions         │
│    Body: {                                                  │
│      "model": "llama-2-70b",                                │
│      "messages": [{"role": "user", "content": "What is 2+2?"}],
│      "temperature": 0.7,                                    │
│      "max_tokens": 1000                                     │
│    }                                                        │
│ 3. unified_chat_completions() in management.py             │
│    - Extract model_id from body                             │
│    - Look up model config in ModelsManager                  │
│    - Determine provider type (vllm/replicate/ollama)       │
│    - Route to appropriate handler                           │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
           ┌───────────────┴───────────────┐
           ▼                               ▼
┌──────────────────────┐      ┌──────────────────────┐
│ vLLM (Local)         │      │ Replicate (Cloud)    │
│ 4a. HTTP POST to     │      │ 4b. POST to          │
│     vLLM server      │      │     replicate API    │
│ 5a. vLLM generates   │      │ 5b. Replicate polls  │
│     response         │      │     prediction       │
│ 6a. Return JSON      │      │ 6b. Return JSON      │
└──────────────────────┘      └──────────────────────┘
           │                               │
           └───────────────┬───────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ GATEWAY (FastAPI)                                            │
│ 7. Format response (OpenAI-compatible)                      │
│    - Record metrics (tokens, latency)                       │
│    - Return HTTP response                                   │
└──────────────────────────┬──────────────────────────────────┘
                           ▼ HTTP 200 OK
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND (LLMPlayground.tsx)                                │  
│ 8. Add assistant message to chat                            │
│    - Update messages state                                  │
│    - Render message in conversation                         │
│    - Scroll to bottom                                       │
│    - Save to history (localStorage)                         │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 Key Components Deep Dive

#### Dashboard (Dashboard.tsx)

**Features:**
- Grid of server cards with status indicators
- Filtering: All / Running / Stopped
- Search by name/description
- Pagination (12 servers per page)
- Quick actions: Start, Stop, View Details

**Data Flow:**
```typescript
useServers() → apiClient.listServers() → 
Backend /api/servers → MongoDB → Response →
State Update → Render Cards
```

#### Tool Runner (ToolRunner.tsx + JsonSchemaForm.tsx)

**Features:**
- Auto-generates forms from JSON Schema
- Supports: strings, numbers, booleans, arrays, objects, enums
- Nested object/array support
- Execution history with localStorage
- Multi-format result viewer (JSON/Table/Text/MCP)

**Form Generation:**
```typescript
// JsonSchemaForm.tsx
const schema = {
  type: "object",
  properties: {
    path: { type: "string" },
    encoding: { type: "string", enum: ["utf8", "base64"] }
  },
  required: ["path"]
};

// Auto-generates:
// - Text input for "path" (required)
// - Select dropdown for "encoding" (optional)
```

#### LLM Playground (LLMPlayground.tsx)

**Features:**
- Model selector with search/filter
- Real-time health monitoring (30s refresh)
- Temperature/max_tokens parameter controls
- Presets: Creative (0.9), Balanced (0.7), Precise (0.3)
- Chat history with max 100 messages
- Clear chat with confirmation
- Request cancellation via AbortController

**State Management:**
```typescript
const [messages, setMessages] = useState<ChatMessage[]>([]);
const [selectedModel, setSelectedModel] = useState<string>('');
const [parameters, setParameters] = useState({ temperature: 0.7, max_tokens: 1000 });
const messagesRef = useRef<ChatMessage[]>([]); // Avoid stale closures
```

**API Call:**
```typescript
const data = await apiClient.chatCompletion({
  model: selectedModel,
  messages: currentMessages,
  temperature: parameters.temperature,
  max_tokens: parameters.max_tokens
}, { signal: abortControllerRef.current.signal });
```

#### Server Details (ServerDetails.tsx)

**Features:**
- Server metadata display
- Tool list with search
- Environment variables viewer
- Real-time logs with tail
- Status polling (every 5 seconds)

**Tabs:**
1. **Tools** - List of available tools with "Run" buttons
2. **Logs** - Live log viewer with refresh
3. **Environment** - Environment variables display

### 5.6 API Communication Pattern

All API calls follow this pattern:

```typescript
// 1. Component calls custom hook
const { servers, startServer } = useServers();

// 2. Hook method calls API client
const startServer = async (id: string) => {
  await apiClient.startServer(id);
  await fetchServers(); // Refresh
};

// 3. API client makes HTTP request
class ApiClient {
  async startServer(serverId: string): Promise<ServerStartResponse> {
    return this.request(`/api/servers/${serverId}/start`, {
      method: 'POST'
    });
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      signal: options?.signal, // AbortController support
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers
      }
    });

    if (!response.ok) {
      throw new ApiHttpError(await response.text(), response.status);
    }

    return response.json();
  }
}
```

**Benefits:**
- Type safety with TypeScript interfaces
- Centralized error handling
- Request cancellation support
- Timeout configuration
- Single source of truth for API calls

---

## 7. Key Features

### 7.1 Chat System (LLM Playground)

**Location:** [fluidmcp/frontend/src/pages/LLMPlayground.tsx](fluidmcp/frontend/src/pages/LLMPlayground.tsx)

**Architecture:**

```
User Input → React State → API Client → 
FastAPI Gateway → LLM Model (vLLM/Replicate/Ollama) → 
Response → State Update → UI Render
```

**Key Features:**

1. **Model Selection:**
   - Dropdown with search/filter
   - Health status indicators (healthy/unhealthy/unknown)
   - Auto-refresh every 30s
   - Model switching clears chat (with confirmation)

2. **Parameter Controls:**
   - Temperature slider (0.0 - 2.0)
   - Max tokens input
   - Presets: Creative (0.9), Balanced (0.7), Precise (0.3)

3. **Chat Interface:**
   - User messages (right-aligned, blue)
   - Assistant messages (left-aligned, gray)
   - Markdown rendering (planned feature)
   - Max 100 messages (prevents memory issues)

4. **Conversation Management:**
   - Clear chat button with confirmation
   - Request cancellation via AbortController
   - Functional setState to avoid race conditions
   - MessagesRef to prevent stale closures

**Implementation Details:**

```typescript
const handleSend = async (e: React.FormEvent) => {
  const userMessage: ChatMessage = { role: 'user', content: input.trim() };
  
  // Functional setState to avoid race conditions
  setMessages(prev => [...prev, userMessage].slice(-MAX_CHAT_MESSAGES));
  
  // Create new AbortController
  abortControllerRef.current = new AbortController();
  
  // API call with cancellation support
  const data = await apiClient.chatCompletion({
    model: selectedModel,
    messages: [...messagesRef.current, userMessage],
    temperature: parameters.temperature,
    max_tokens: parameters.max_tokens
  }, { signal: abortControllerRef.current.signal });
  
  // Add assistant response
  setMessages(prev => [...prev, {
    role: 'assistant',
    content: data.choices[0].message.content
  }].slice(-MAX_CHAT_MESSAGES));
};
```

**API Endpoint:**
```
POST /api/llm/v1/chat/completions
```

**Request Format (OpenAI-Compatible):**
```json
{
  "model": "llama-2-70b",
  "messages": [
    {"role": "user", "content": "What is 2+2?"}
  ],
  "temperature": 0.7,
  "max_tokens": 1000
}
```

**Response Format:**
```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "2+2 equals 4."
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 10,
    "completion_tokens": 8,
    "total_tokens": 18
  }
}
```

**Streaming Support:**
- Backend supports streaming via Server-Sent Events (SSE)
- Frontend implementation planned but not yet enabled
- Streaming API: Set `"stream": true` in request body
- Response format: `data: {...}\n\ndata: [DONE]\n\n`

### 7.2 Logs System

**Backend Implementation:**

```python
# server_manager.py
async def get_server_logs(self, server_id: str, lines: int = 100):
    """Get last N lines of server stderr logs"""
    log_file = f"~/.fluidmcp/logs/{sanitized_server_id}_stderr.log"
    
    # Read with tail-like behavior
    with open(log_file, 'r') as f:
        all_lines = f.readlines()
        return all_lines[-lines:]  # Last N lines
```

**Frontend Implementation:**

[ServerDetails.tsx](fluidmcp/frontend/src/pages/ServerDetails.tsx) - Logs Tab
- Fetches logs via `GET /api/servers/{id}/logs?lines=100`
- Auto-refresh option (every 5 seconds)
- Line count selector (50, 100, 200, 500, 1000)
- Syntax highlighting for structured logs
- Error line highlighting

**Log Files Location:**
```
~/.fluidmcp/logs/
├── {server_id}_stderr.log       # MCP server errors
├── {server_id}_stdout.log       # MCP server output (rare)
└── llm_{model_id}_stderr.log    # LLM model logs
```

**Security:**
- Log files created with `0o600` permissions (owner read/write only)
- Sensitive data redacted (API keys, tokens, passwords)
- Path sanitization prevents directory traversal

### 7.3 Tool Execution via JSON Schema

**Dynamic Form Generation:**

FluidMCP automatically generates forms from MCP tool schemas using [JsonSchemaForm.tsx](fluidmcp/frontend/src/components/form/JsonSchemaForm.tsx):

**JSON Schema Example:**
```json
{
  "name": "search_files",
  "description": "Search for files matching a pattern",
  "inputSchema": {
    "type": "object",
    "properties": {
      "pattern": {
        "type": "string",
        "description": "Glob pattern (e.g., *.ts)"
      },
      "recursive": {
        "type": "boolean",
        "description": "Search recursively",
        "default": true
      },
      "max_results": {
        "type": "number",
        "description": "Maximum results to return",
        "default": 10
      },
      "file_types": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Filter by file extensions"
      }
    },
    "required": ["pattern"]
  }
}
```

**Generated Form:**
- Text input for `pattern` (required, red asterisk)
- Checkbox for `recursive` (default checked)
- Number input for `max_results` (default 10)
- Multi-input for `file_types` (add/remove buttons)

**Form Submission:**
```typescript
// useToolRunner.ts
const runTool = async (args: Record<string, any>) => {
  const result = await apiClient.runTool(serverId, toolName, {
    name: toolName,
    arguments: args
  });
  
  // Save to history (localStorage)
  toolHistoryService.saveExecution({
    serverId,
    toolName,
    arguments: args,
    result: result.content,
    duration: result.duration
  });
  
  return result;
};
```

**Result Rendering:**

[ToolResult.tsx](fluidmcp/frontend/src/components/result/ToolResult.tsx) auto-detects format:

1. **MCP Content Format:** Renders specialized content blocks
   ```json
   {
     "content": [
       {"type": "text", "text": "Hello"},
       {"type": "image", "data": "base64...", "mimeType": "image/png"}
     ]
   }
   ```

2. **JSON:** Syntax-highlighted JSON viewer

3. **Table:** Auto-converts arrays of objects to tables

4. **Plain Text:** Monospace text display

**Tool History:**

Stored in `localStorage` with [toolHistory.ts](fluidmcp/frontend/src/services/toolHistory.ts):
```typescript
interface ToolExecution {
  id: string;
  serverId: string;
  toolName: string;
  arguments: Record<string, any>;
  result: any;
  duration?: number;
  timestamp: string;
  status: 'success' | 'error';
}
```

**Features:**
- Recent arguments auto-populate form
- Execution history viewer
- Clear history option
- Max 1000 executions per tool (LRU eviction)

---

## 8. Important Files and Folders

### 8.1 Project Structure

```
fluidmcp/
├── cli/                          # Backend Python code
│   ├── __init__.py              # Package entry point
│   ├── __main__.py              # Module execution handler
│   ├── cli.py                   # ⭐ Main CLI with argparse
│   ├── server.py                # ⭐ FastAPI server entry point
│   ├── auth.py                  # Bearer token authentication
│   │
│   ├── api/                     # FastAPI route handlers
│   │   ├── management.py        # ⭐ Management & LLM endpoints
│   │   └── frontend.py          # Static file serving for React
│   │
│   ├── services/                # Core business logic
│   │   ├── config_resolver.py  # ⭐ 5 configuration sources
│   │   ├── package_launcher.py # ⭐ MCP server subprocess mgmt
│   │   ├── run_servers.py      # ⭐ Unified server launcher
│   │   ├── server_manager.py   # ⭐ Dynamic lifecycle mgmt
│   │   ├── llm_launcher.py     # ⭐ vLLM/Ollama orchestration
│   │   ├── replicate_client.py # Replicate API client
│   │   ├── package_installer.py # Registry downloads
│   │   ├── github_utils.py     # GitHub cloning & metadata
│   │   ├── metrics.py          # Prometheus metrics
│   │   ├── network_utils.py    # Port management
│   │   └── env_manager.py      # Environment variable handling
│   │
│   └── persistence/             # Database layer
│       ├── database.py          # MongoDB connection
│       ├── models.py            # Data models (Server, LLM)
│       └── backends/            # Storage backends
│           ├── mongodb_backend.py  # MongoDB implementation
│           └── memory_backend.py   # In-memory fallback
│
├── frontend/                     # React web UI
│   ├── src/
│   │   ├── pages/               # ⭐ 9 main routes/pages
│   │   ├── components/          # Reusable UI components
│   │   ├── hooks/               # ⭐ 14 custom hooks
│   │   ├── services/            # ⭐ API client & utilities
│   │   └── types/               # TypeScript type definitions
│   ├── package.json             # npm dependencies
│   └── vite.config.ts           # Vite build configuration
│
├── examples/                     # Sample configurations
│   ├── sample-config.json       # Basic MCP servers
│   ├── replicate-inference.json # Replicate cloud models
│   ├── vllm-with-error-recovery.json # vLLM local inference
│   └── README.md                # Testing guide
│
├── docs/                         # Technical documentation
│   ├── RAILWAY_DEPLOYMENT.md    # Production deployment guide
│   ├── REPLICATE_SUPPORT.md     # Cloud inference docs
│   ├── VLLM_ERROR_RECOVERY.md   # Error handling & restarts
│   ├── FUNCTION_CALLING.md      # Function calling support
│   └── TROUBLESHOOTING.md       # Common issues
│
├── tests/                        # Test suite
│   ├── test_llm_security.py     # LLM security tests (18)
│   ├── test_llm_integration.py  # LLM integration tests (10)
│   ├── test_streaming.py        # Streaming tests
│   └── test_*.py                # 30+ test files
│
├── requirements.txt              # Python dependencies
├── setup.py                      # Package configuration
├── Dockerfile                    # Production container
├── CLAUDE.md                     # ⭐ Developer quick reference
└── README.md                     # User-facing documentation
```

### 8.2 Critical Files to Understand

#### Backend Core

**[cli.py](fluidmcp/cli/cli.py)** (600 lines)
- Command-line argument parsing with argparse
- Command routing: `install`, `run`, `serve`, `github`, `list`, `edit-env`, `validate`
- Environment variable handling
- Error handling and logging setup

**[server.py](fluidmcp/cli/server.py)** (500 lines)
- FastAPI application factory: `create_app()`
- MongoDB connection with retry logic
- CORS configuration (secure by default)
- Background task setup
- Model restoration from persistence
- Health endpoint implementation

**[package_launcher.py](fluidmcp/cli/services/package_launcher.py)** (800 lines)
- `launch_mcp_using_fastapi_proxy()` - Spawns MCP server subprocess
- `initialize_mcp_server()` - JSON-RPC handshake
- `create_mcp_router()` - Creates FastAPI routes per server
- Thread-safe stdio communication
- Working directory resolution
- HTTP header injection

**[server_manager.py](fluidmcp/cli/services/server_manager.py)** (1000+ lines)
- `ServerManager` class - Central orchestrator
- Dynamic server lifecycle: `start_server()`, `stop_server()`, `restart_server()`
- Tool discovery and caching
- Log management
- Status tracking
- Operation locking (prevents concurrent operations)

**[management.py](fluidmcp/cli/api/management.py)** (3000+ lines)
- All REST API endpoints
- `unified_chat_completions()` - Routes to vLLM/Replicate/Ollama
- Server CRUD operations
- Model registration and management
- Rate limiting (optional, requires Redis)
- Metrics collection

#### Frontend Core

**[App.tsx](fluidmcp/frontend/src/App.tsx)** (150 lines)
- React Router setup with 9 routes
- Layout with Navbar and Footer
- Route configuration

**[api.ts](fluidmcp/frontend/src/services/api.ts)** (600 lines)
- `ApiClient` class - Singleton HTTP client
- 30+ typed methods for all API endpoints
- Timeout handling (30s default, 120s for GitHub)
- AbortController integration
- Error handling with `ApiHttpError`

**[useToolRunner.ts](fluidmcp/frontend/src/hooks/useToolRunner.ts)** (200 lines)
- Tool execution logic
- History management
- State management for ToolRunner page

**[JsonSchemaForm.tsx](fluidmcp/frontend/src/components/form/JsonSchemaForm.tsx)** (400 lines)
- Dynamic form generation from JSON Schema
- Supports all JSON Schema types
- Nested objects and arrays
- Validation with Zod

**[LLMPlayground.tsx](fluidmcp/frontend/src/pages/LLMPlayground.tsx)** (500 lines)
- Chat interface implementation
- Model selection and health monitoring
- Parameter controls
- Message state management

### 8.3 Configuration Files

**[requirements.txt](requirements.txt)** - Python dependencies
- FastAPI, Uvicorn, Pydantic
- Motor (async MongoDB driver)
- httpx, aiohttp (HTTP clients)
- pytest, pytest-asyncio (testing)

**[frontend/package.json](fluidmcp/frontend/package.json)** - npm dependencies
- React, React Router
- Radix UI components
- Tailwind CSS
- React Hook Form, Zod

**[Dockerfile](Dockerfile)** - Production container
- Multi-stage build (frontend + backend)
- Frontend: Node.js → Vite build → static files
- Backend: Python → FastAPI server
- Entry point: `fmcp serve` with MongoDB
- Health checks configured

**[pytest.ini](pytest.ini)** - Test configuration
- Test discovery patterns
- Coverage settings
- Async test configuration

### 8.4 Directory Purposes

| Directory | Purpose |
|-----------|---------|
| `fluidmcp/cli/` | Backend Python code (CLI, API, services) |
| `fluidmcp/frontend/` | React web UI (TypeScript + Vite) |
| `fluidmcp/cli/api/` | FastAPI route handlers |
| `fluidmcp/cli/services/` | Core business logic (server mgmt, LLM, etc.) |
| `fluidmcp/cli/persistence/` | Database layer (MongoDB + in-memory) |
| `examples/` | Sample configurations and test scripts |
| `docs/` | Technical documentation (deployment, features) |
| `tests/` | Test suite (pytest, 40+ test files) |
| `scripts/` | Utility scripts (model registration, etc.) |
| `Skills/` | Agent customizations and tutorials |
| `~/.fluidmcp/` | User data directory (logs, packages) |
| `.fmcp-packages/` | Installed MCP packages and GitHub repos |

---

## 9. Developer Workflow

### 9.1 Initial Setup

```bash
# Clone repository
git clone https://github.com/Fluid-AI/fluidmcp.git
cd fluidmcp

# Install Python dependencies
pip install -r requirements.txt

# Install package in development mode
pip install -e .

# Verify installation
fmcp --version

# Optional: Install MongoDB for persistence (development)
docker run -d -p 27017:27017 --name mongodb mongo:latest
export MONGODB_URI="mongodb://localhost:27017"
```

### 9.2 Running the Project Locally

#### Option A: Run with Sample Config (Quick Test)

```bash
# Use sample config (no installation required)
fmcp run examples/sample-config.json --file --start-server

# Server starts on http://localhost:8099
# Swagger UI: http://localhost:8099/docs
# Web UI: http://localhost:8099

# Test an endpoint
curl -X POST http://localhost:8099/filesystem/mcp/tools/list
```

#### Option B: Run in Serve Mode (Production-Like)

```bash
# Start MongoDB (required for persistence)
docker run -d -p 27017:27017 --name mongodb mongo:latest

# Set environment
export MONGODB_URI="mongodb://localhost:27017"
export FMCP_BEARER_TOKEN=$(openssl rand -hex 32)

# Start server
fmcp serve --port 8099

# Access UI
open http://localhost:8099

# Add servers via API
curl -X POST http://localhost:8099/api/servers \
  -H "Authorization: Bearer $FMCP_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "filesystem",
    "config": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
      "env": {}
    }
  }'

# Start the server
curl -X POST http://localhost:8099/api/servers/filesystem/start \
  -H "Authorization: Bearer $FMCP_BEARER_TOKEN"
```

#### Option C: Frontend Development

```bash
# Build frontend first
cd fluidmcp/frontend
npm install
npm run build

# Start FluidMCP server (serves both backend & frontend)
cd ../..
fmcp serve --port 8099

# Access in browser:
# - Codespaces: https://<codespace-name>.github.dev/ui
# - Localhost: http://localhost:8099
# - API Docs: https://<codespace-name>.github.dev/docs or http://localhost:8099/docs
```

### 9.3 How to Add a New MCP Server

#### Method 1: Via Configuration File

**Step 1:** Create config file

```json
{
  "mcpServers": {
    "my-new-server": {
      "command": "python",
      "args": ["-m", "my_mcp_server"],
      "env": {
        "API_KEY": "your-api-key-here"
      }
    }
  }
}
```

**Step 2:** Run FluidMCP

```bash
fmcp run my-config.json --file --start-server
```

#### Method 2: Via GitHub Repository

**Step 1:** Prepare your repository

Ensure your repo has either:
- `metadata.json` in root or subdirectory
- Or README.md with structured MCP metadata

**Step 2:** Clone and run

```bash
export GITHUB_TOKEN="ghp_..."
fmcp github owner/repo --github-token $GITHUB_TOKEN --start-server
```

#### Method 3: Via REST API (Dynamic)

**Step 1:** Start FluidMCP in serve mode

```bash
export MONGODB_URI="mongodb://localhost:27017"
fmcp serve
```

**Step 2:** Add server via API

```bash
curl -X POST http://localhost:8099/api/servers \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "my-new-server",
    "config": {
      "command": "python",
      "args": ["-m", "my_mcp_server"],
      "env": {"API_KEY": "secret"}
    }
  }'
```

**Step 3:** Start the server

```bash
curl -X POST http://localhost:8099/api/servers/my-new-server/start
```

### 9.4 How to Test Tools

#### Option 1: Via Web UI (Easiest)

1. Open http://localhost:8099
2. Navigate to server (Dashboard → Click server card)
3. Go to "Tools" tab
4. Click "Run" on a tool
5. Fill auto-generated form
6. Click "Execute"
7. View results

#### Option 2: Via REST API

```bash
# List available tools
curl -X GET http://localhost:8099/filesystem/mcp/tools/list

# Execute a tool
curl -X POST http://localhost:8099/filesystem/mcp/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "name": "read_file",
    "arguments": {
      "path": "/tmp/test.txt"
    }
  }'
```

#### Option 3: Via JSON-RPC (Direct)

```bash
# Generic MCP endpoint (raw JSON-RPC)
curl -X POST http://localhost:8099/filesystem/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "read_file",
      "arguments": {"path": "/tmp/test.txt"}
    }
  }'
```

#### Option 4: Via Python Client

```python
import httpx

async def test_tool():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8099/filesystem/mcp/tools/call",
            json={
                "name": "read_file",
                "arguments": {"path": "/tmp/test.txt"}
            }
        )
        print(response.json())
```

### 9.5 Running Tests

```bash
# Run all tests
pytest

# Run specific test suite
pytest tests/test_llm_security.py      # Security tests (18 tests)
pytest tests/test_llm_integration.py   # Integration tests (10 tests)
pytest tests/test_streaming.py         # Streaming tests

# Run with coverage
pytest --cov=fluidmcp --cov-report=html

# Run manual integration tests
python tests/manual/integration_test_streaming.py
```

**Test Organization:**
- `tests/test_*.py` - Unit and integration tests
- `tests/manual/` - Manual integration tests (require running server)
- Coverage target: >80% for core services

### 9.6 Common Development Tasks

#### Add a New API Endpoint

**Step 1:** Add endpoint to [management.py](fluidmcp/cli/api/management.py)

```python
@router.get("/api/my-new-endpoint")
async def my_new_endpoint(token: str = Depends(get_token)):
    """My new endpoint description"""
    # Implementation
    return {"status": "success"}
```

**Step 2:** Add TypeScript method to [api.ts](fluidmcp/frontend/src/services/api.ts)

```typescript
async myNewEndpoint(options?: { signal?: AbortSignal }): Promise<MyResponse> {
  return this.request<MyResponse>('/api/my-new-endpoint', {
    method: 'GET',
    signal: options?.signal
  });
}
```

**Step 3:** Use in a React component

```typescript
const MyComponent = () => {
  const [data, setData] = useState(null);

  useEffect(() => {
    apiClient.myNewEndpoint().then(setData);
  }, []);

  return <div>{JSON.stringify(data)}</div>;
};
```

#### Add a New Frontend Page

**Step 1:** Create page component

```typescript
// pages/MyNewPage.tsx
export default function MyNewPage() {
  return (
    <div className="min-h-screen bg-black text-white">
      <Navbar />
      <div className="pt-16">
        <h1>My New Page</h1>
      </div>
      <Footer />
    </div>
  );
}
```

**Step 2:** Add route to [App.tsx](fluidmcp/frontend/src/App.tsx)

```typescript
<Route path="/my-new-page" element={<MyNewPage />} />
```

**Step 3:** Add navigation link to [Navbar.tsx](fluidmcp/frontend/src/components/Navbar.tsx)

```typescript
<Link to="/my-new-page" className="nav-link">
  My New Page
</Link>
```

#### Add Environment Variable Support

**Step 1:** Document in [CLAUDE.md](CLAUDE.md)

```markdown
# Environment Variables
MY_NEW_VAR="value"  # Description of what it does
```

**Step 2:** Access in Python code

```python
import os
my_var = os.getenv("MY_NEW_VAR", "default-value")
```

**Step 3:** Add to [Dockerfile](Dockerfile) if needed

```dockerfile
ENV MY_NEW_VAR=""
```

#### Debug a Server Issue

**Step 1:** Check logs

```bash
# Check server logs
tail -f ~/.fluidmcp/logs/{server_id}_stderr.log

# Or via API
curl http://localhost:8099/api/servers/{server_id}/logs?lines=100
```

**Step 2:** Test server directly (bypass gateway)

```bash
# Find command from metadata
cat .fmcp-packages/Author/Package/Version/metadata.json

# Run command manually
npx -y @modelcontextprotocol/server-filesystem /tmp

# Then send JSON-RPC manually:
{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {...}}
```

**Step 3:** Enable debug logging

```python
# Add to code
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 9.7 Build and Deploy

#### Local Development Build

```bash
# Backend: No build needed (Python)
pip install -e .

# Frontend: Build for production
cd fluidmcp/frontend
npm run build
# Output: fluidmcp/frontend/dist/
```

#### Docker Build

```bash
# Build container
docker build -t fluidmcp:latest .

# Run container
docker run -d -p 8099:8099 \
  -e MONGODB_URI="mongodb://host.docker.internal:27017" \
  -e FMCP_BEARER_TOKEN="your-token-here" \
  fluidmcp:latest

# Health check
curl http://localhost:8099/health
```

#### Railway Deployment

See [docs/RAILWAY_DEPLOYMENT.md](docs/RAILWAY_DEPLOYMENT.md) for complete guide.

**Quick steps:**
1. Add MongoDB service in Railway
2. Connect GitHub repo (branch: `main`)
3. Set `FMCP_BEARER_TOKEN` environment variable
4. Railway auto-deploys using [Dockerfile](Dockerfile)
5. Access via Railway-provided URL

**Critical Environment Variables:**
- `MONGODB_URI` - Auto-provided by Railway MongoDB service
- `FMCP_BEARER_TOKEN` - **Must set manually** (prevents token regeneration)
- `PORT` - Auto-assigned by Railway

---

## Additional Resources

### Documentation

- **[CLAUDE.md](CLAUDE.md)** - Quick reference for Claude/AI assistants
- **[README.md](README.md)** - User-facing documentation
- **[docs/RAILWAY_DEPLOYMENT.md](docs/RAILWAY_DEPLOYMENT.md)** - Production deployment
- **[docs/REPLICATE_SUPPORT.md](docs/REPLICATE_SUPPORT.md)** - Cloud inference guide
- **[docs/FUNCTION_CALLING.md](docs/FUNCTION_CALLING.md)** - Function calling support
- **[docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)** - Common issues and solutions

### Example Configurations

- **[examples/sample-config.json](examples/sample-config.json)** - Basic filesystem + memory servers
- **[examples/replicate-inference.json](examples/replicate-inference.json)** - Cloud inference
- **[examples/vllm-with-error-recovery.json](examples/vllm-with-error-recovery.json)** - Local inference
- **[examples/README.md](examples/README.md)** - Testing guide with examples

### Testing

- **[tests/README.md](tests/README.md)** - Test suite overview
- 40+ test files covering all major features
- Manual test scripts in `tests/manual/`

### Architecture Documentation

- **[CODE_FLOW.md](CODE_FLOW.md)** - Code flow analysis
- **[Skills/code_flow/](Skills/code_flow/)** - Detailed architecture diagrams
- **[Skills/tutorial/](Skills/tutorial/)** - Concept and usage tutorials

---

## Glossary

**MCP (Model Context Protocol):** JSON-RPC protocol for AI tool execution

**Gateway:** FastAPI server that routes requests to MCP servers

**stdio:** Standard input/output (pipe-based communication)

**JSON-RPC 2.0:** Remote procedure call protocol using JSON

**Tool:** A function exposed by an MCP server (e.g., `read_file`, `search_web`)

**Package:** Installable MCP server from FluidMCP registry

**Server Manager:** Component that handles dynamic server lifecycle

**Unified Endpoint:** Single API endpoint that routes to multiple backends (e.g., `/api/llm/v1/chat/completions`)

**Bearer Token:** Authentication token for secure API access

**Persistence:** MongoDB-based storage for server and model configurations

---

## Next Steps

1. **Read** [CLAUDE.md](CLAUDE.md) for quick command reference
2. **Explore** [examples/](examples/) directory for sample configurations
3. **Run** a sample config: `fmcp run examples/sample-config.json --file --start-server`
4. **Browse** the UI at http://localhost:8099
5. **Execute** a tool via the Tool Runner page
6. **Review** architecture diagrams in [Skills/code_flow/](Skills/code_flow/)
7. **Read** test files to understand component behavior

---

**Questions or Issues?**
- Check [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- Review test files for usage examples
- Read inline code comments for implementation details

**Welcome to FluidMCP!** 🚀
