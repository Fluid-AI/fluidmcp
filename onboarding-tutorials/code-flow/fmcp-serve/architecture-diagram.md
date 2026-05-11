# fmcp serve — Architecture Diagram

> Standalone FluidMCP backend: CLI dispatches to an async FastAPI gateway that manages MCP server subprocesses and LLM models through layered routers, authenticated via bearer token, and persisted to MongoDB or in-memory storage.

## System Architecture

`fmcp serve` starts an always-on FastAPI server that exposes a management REST API for dynamically adding, starting, stopping, and proxying MCP server subprocesses. Persistence is provided by either a Motor-async MongoDB client or a purely in-memory backend, selected at startup.

```
┌── LAYER 1: ENTRY / CLI ──────────────────────────────────────────────────────────────────────┐
│                                                                                               │
│   ┌─────────────────────────────────────────┐                                                │
│   │  fmcp serve  (user invocation)          │                                                │
│   │  cli/cli.py · serve_parser (argparse)   │                                                │
│   │  Flags: --secure --port --mongodb-uri   │                                                │
│   │         --in-memory --require-persist.. │                                                │
│   └──────────────────┬──────────────────────┘                                                │
│                      │ asyncio.run()                                                          │
│                      ▼                                                                        │
│   ┌─────────────────────────────────────────┐                                                │
│   │  server.py · main(args)                 │                                                │
│   │  1. Choose persistence backend          │                                                │
│   │  2. Create ServerManager                │                                                │
│   │  3. Start background tasks              │                                                │
│   │  4. Call create_app()                   │                                                │
│   │  5. Load models from persistence        │                                                │
│   │  6. Run uvicorn Server                  │                                                │
│   └─────────────────────────────────────────┘                                                │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
        │ await create_app(db_manager, server_manager, ...)
        ▼
┌── LAYER 2: FASTAPI APP ──────────────────────────────────────────────────────────────────────┐
│                                                                                               │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐    │
│   │  server.py · create_app()  →  FastAPI(title="FluidMCP Gateway", version="2.0.0")   │    │
│   │                                                                                     │    │
│   │  Middleware stack (outermost → innermost):                                          │    │
│   │  ┌───────────────────────────────────────────────────────────────────────────────┐ │    │
│   │  │  CORSMiddleware  (fastapi.middleware.cors)                                     │ │    │
│   │  │  Origins: localhost only by default; wildcard allowed via --allow-all-origins  │ │    │
│   │  └───────────────────────────────────────────────────────────────────────────────┘ │    │
│   │  ┌───────────────────────────────────────────────────────────────────────────────┐ │    │
│   │  │  limit_request_size  (@app.middleware("http"))                                 │ │    │
│   │  │  Content-Length check; default 10 MB; env MAX_REQUEST_SIZE_MB                 │ │    │
│   │  │  Returns HTTP 413 on violation                                                 │ │    │
│   │  └───────────────────────────────────────────────────────────────────────────────┘ │    │
│   │                                                                                     │    │
│   │  Built-in endpoints:                                                                │    │
│   │  ┌──────────────┐   ┌───────────────────────────────────────┐                     │    │
│   │  │ GET /health  │   │ GET /metrics  (auth: verify_token)     │                     │    │
│   │  │ (public)     │   │ Prometheus text/plain v0.0.4           │                     │    │
│   │  └──────────────┘   └───────────────────────────────────────┘                     │    │
│   │  ┌──────────────┐                                                                  │    │
│   │  │ GET /        │  (root info endpoint, public)                                    │    │
│   │  └──────────────┘                                                                  │    │
│   │                                                                                     │    │
│   │  Lifespan (asynccontextmanager):                                                    │    │
│   │  • startup  →  Inspector session cleanup task                                      │    │
│   │  • shutdown →  HTTP client cleanup, Redis cleanup, DB disconnect                   │    │
│   └─────────────────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
        │                         │                              │
        ▼                         ▼                              ▼
┌── LAYER 3: AUTH (cross-cutting dependency) ──────────────────────────────────────────────────┐
│                                                                                               │
│   ┌─────────────────────────────────────────────────────────────────────────────────────┐    │
│   │  auth.py · verify_token(credentials: HTTPAuthorizationCredentials)                  │    │
│   │                                                                                     │    │
│   │  • FastAPI Depends() injected into any protected route                              │    │
│   │  • Reads env: FMCP_SECURE_MODE, FMCP_BEARER_TOKEN                                  │    │
│   │  • If secure mode OFF  →  passes through (public access)                           │    │
│   │  • If secure mode ON   →  delegates to _validate_bearer_token()                    │    │
│   │    - scheme must be "bearer"                                                        │    │
│   │    - secrets.compare_digest() for constant-time comparison (timing-attack safe)    │    │
│   │    - HTTP 401 + WWW-Authenticate header on failure                                  │    │
│   │    - HTTP 500 if FMCP_BEARER_TOKEN not configured                                  │    │
│   │                                                                                     │    │
│   │  Also available: get_token() — same flow but returns token string                  │    │
│   └─────────────────────────────────────────────────────────────────────────────────────┘    │
│                                                                                               │
│   Applied to:  /metrics  ·  inspector_router (all routes)  ·  mgmt_router (per-route)        │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
        │                         │                              │
        ▼                         ▼                              ▼
┌── LAYER 4: ROUTERS ──────────────────────────────────────────────────────────────────────────┐
│                                                                                               │
│  ┌─────────────────────────────────────────┐  ┌──────────────────────────────────────────┐  │
│  │  api/management.py · mgmt_router        │  │  api/inspector.py · inspector_router      │  │
│  │  prefix: /api   tag: management         │  │  prefix: /api   tag: inspector            │  │
│  │                                         │  │  global dep: Depends(verify_token)        │  │
│  │  MCP Server CRUD:                       │  │                                           │  │
│  │   POST   /api/servers                   │  │  POST   /api/inspector/connect            │  │
│  │   POST   /api/servers/from-github       │  │  GET    /api/inspector/{id}/tools         │  │
│  │   GET    /api/servers                   │  │  POST   /api/inspector/{id}/tools/{name}  │  │
│  │   GET    /api/servers/{id}              │  │         /run                              │  │
│  │   PUT    /api/servers/{id}              │  │  DELETE /api/inspector/{id}               │  │
│  │   DELETE /api/servers/{id}              │  └──────────────────────────────────────────┘  │
│  │                                         │                                                 │
│  │  Lifecycle:                             │  ┌──────────────────────────────────────────┐  │
│  │   POST /api/servers/{id}/start          │  │  Dynamic MCP proxy router                 │  │
│  │   POST /api/servers/{id}/stop           │  │  services/package_launcher.py             │  │
│  │   POST /api/servers/{id}/restart        │  │  create_dynamic_router(server_manager)    │  │
│  │   POST /api/servers/start-all           │  │                                           │  │
│  │   POST /api/servers/stop-all            │  │  Mounted at root (no prefix)              │  │
│  │                                         │  │  Routes: /{server_name}/mcp               │  │
│  │  Proxy / SSE:                           │  │  Forwards JSON-RPC to running subprocess  │  │
│  │   GET  /api/servers/{id}/sse            │  └──────────────────────────────────────────┘  │
│  │   POST /api/servers/{id}/messages       │                                                 │
│  │                                         │                                                 │
│  │  Status / Logs / Env:                   │                                                 │
│  │   GET  /api/servers/{id}/status         │                                                 │
│  │   GET  /api/servers/{id}/logs           │                                                 │
│  │   GET  /api/servers/{id}/tools          │                                                 │
│  │   POST /api/servers/{id}/tools/*/run    │                                                 │
│  │   GET/PUT/DELETE  .../instance/env      │                                                 │
│  │                                         │                                                 │
│  │  LLM sub-routes (within mgmt_router):   │                                                 │
│  │   POST /api/llm/models                  │                                                 │
│  │   GET  /api/llm/models                  │                                                 │
│  │   GET  /api/llm/models/{id}             │                                                 │
│  │   POST /api/llm/models/{id}/start|stop  │                                                 │
│  │        /restart /health-check /logs     │                                                 │
│  │   PATCH/DELETE /api/llm/models/{id}     │                                                 │
│  │   POST /api/llm/models/{id}/rollback    │                                                 │
│  │                                         │                                                 │
│  │  OpenAI-compatible inference:           │                                                 │
│  │   POST /api/llm/v1/chat/completions     │                                                 │
│  │   POST /api/llm/v1/completions          │                                                 │
│  │   GET  /api/llm/v1/models[/{id}]        │                                                 │
│  │                                         │                                                 │
│  │  Multimodal (Omni / Replicate):         │                                                 │
│  │   POST /api/llm/v1/generate/image       │                                                 │
│  │   POST /api/llm/v1/generate/video       │                                                 │
│  │   POST /api/llm/v1/animate              │                                                 │
│  │   GET  /api/llm/predictions/{id}        │                                                 │
│  │                                         │                                                 │
│  │  Metrics:                               │                                                 │
│  │   GET  /api/metrics                     │                                                 │
│  │   GET  /api/metrics/json                │                                                 │
│  │   POST /api/metrics/reset               │                                                 │
│  └─────────────────────────────────────────┘                                                 │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
        │                                          │
        ▼                                          ▼
┌── LAYER 5: SERVICES ─────────────────────────────────────────────────────────────────────────┐
│                                                                                               │
│  ┌──────────────────────────────────────────────────────────────────────────────────────┐    │
│  │  services/server_manager.py · ServerManager                                          │    │
│  │                                                                                      │    │
│  │  Responsibilities:                                                                   │    │
│  │  • Process registry: Dict[server_id → subprocess.Popen]                             │    │
│  │  • start / stop / restart individual servers (async, per-server lock)               │    │
│  │  • shutdown_all() — graceful SIGTERM then SIGKILL fallback                          │    │
│  │  • get_uptime(server_id)  — monotonic clock tracking                                │    │
│  │  • start_idle_cleanup_task()  — auto-stop servers idle > FMCP_IDLE_TIMEOUT          │    │
│  │  • _cleanup_on_exit()  — atexit handler                                             │    │
│  │  • Delegates persistence calls to db (PersistenceBackend)                           │    │
│  │  • Stderr captured to log files (file handles in _stderr_logs)                      │    │
│  └──────────────────────────────────────────────────────────────────────────────────────┘    │
│            - - ►  (background asyncio.Task)                                                   │
│  ┌──────────────────────────────────────────────────────────────────────────────────────┐    │
│  │  services/server_manager.py · MCPHealthMonitor                                       │    │
│  │                                                                                      │    │
│  │  • Wraps ServerManager                                                               │    │
│  │  • _monitor_loop() runs every FMCP_HEALTH_CHECK_INTERVAL seconds (default 30s)      │    │
│  │  • Detects crashed processes (poll() != None)                                        │    │
│  │  • Exponential-backoff auto-restart (MAX_BACKOFF_EXPONENT=5, base delay 5s)         │    │
│  │  • Tracks _restart_counts per server_id                                             │    │
│  │  • start() / stop() control the asyncio.Task lifecycle                              │    │
│  └──────────────────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
        │ await db.*                               │ await db.*
        ▼                                          ▼
┌── LAYER 6: PERSISTENCE ──────────────────────────────────────────────────────────────────────┐
│                                                                                               │
│  Selected at startup by --persistence-mode / --in-memory flag                                │
│                                                                                               │
│  ┌────────────────────────────────────────────┐  ┌────────────────────────────────────────┐  │
│  │  repositories/database.py · DatabaseManager│  │  repositories/memory.py                │  │
│  │  (implements PersistenceBackend)            │  │  · InMemoryBackend                     │  │
│  │                                             │  │  (implements PersistenceBackend)       │  │
│  │  __init__(mongodb_uri, database_name)       │  │                                        │  │
│  │  • Motor async client (AsyncIOMotorClient)  │  │  • Pure Python dicts / deques          │  │
│  │  • init_db() — creates indexes             │  │  • connect() → always True             │  │
│  │  • connect_with_retry() — 3 attempts,       │  │  • disconnect() → clears all dicts     │  │
│  │    exp backoff 2s/4s/8s (server.py)         │  │  • No network I/O                      │  │
│  │  • disconnect() — graceful Motor close      │  │  • _servers / _instances / _logs       │  │
│  │  • save/get/list/delete server configs      │  │    / _llm_models / _crash_events       │  │
│  │  • log writes → LogBuffer on failure        │  │  • Data lost on process restart        │  │
│  │  • _sanitize_mongodb_input() — strips $     │  │  • Suitable for dev / testing          │  │
│  │    operators (injection prevention)         │  └────────────────────────────────────────┘  │
│  └────────────────────────────────────────────┘                                               │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
        │ Motor async TCP                                   │ (no I/O)
        ▼                                                   ▼
┌── LAYER 7: EXTERNAL ─────────────────────────────────────────────────────────────────────────┐
│                                                                                               │
│  ┌────────────────────────────────────────┐   ┌──────────────────────────────────────────┐  │
│  │  MongoDB (Motor async client)          │   │  MCP subprocesses                         │  │
│  │  • Connection string: MONGODB_URI      │   │  (npx / python / custom command)          │  │
│  │  • Default: mongodb://localhost:27017  │   │                                           │  │
│  │  • Database: "fluidmcp" (configurable) │   │  • Spawned by ServerManager via           │  │
│  │  • Collections:                        │   │    subprocess.Popen                       │  │
│  │    - server_configs                    │   │  • Communicate via stdin/stdout (MCP      │  │
│  │    - instances                         │   │    JSON-RPC protocol) or SSE              │  │
│  │    - logs                              │   │  • stderr → file (~/.fluidmcp/logs/)      │  │
│  │    - llm_models                        │   │  • Monitored by MCPHealthMonitor          │  │
│  │    - crash_events                      │   │  • Auto-restarted on crash                │  │
│  └────────────────────────────────────────┘   └──────────────────────────────────────────┘  │
│                                                                                               │
│  ┌────────────────────────────────────────┐   ┌──────────────────────────────────────────┐  │
│  │  Replicate Cloud API                   │   │  Sentry (opt-in)                          │  │
│  │  • HTTP polling client                 │   │  • SENTRY_DSN env var                     │  │
│  │  • Used for: chat completions,         │   │  • FastApiIntegration + AsyncioIntegration│  │
│  │    image/video generation, animation   │   │  • /health and /metrics excluded          │  │
│  └────────────────────────────────────────┘   └──────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### Request flow — example: POST /api/servers/{id}/start

```
HTTP client
    │
    │  POST /api/servers/{id}/start
    │  Authorization: Bearer <token>
    ▼
CORSMiddleware  ───►  limit_request_size middleware
    │
    ▼
mgmt_router  (api/management.py)
    │
    ├── Depends(verify_token)  ────►  auth.py · verify_token()
    │       │                              │
    │       │  FMCP_SECURE_MODE=true       │  secrets.compare_digest()
    │       │                              │  HTTP 401 on mismatch
    │       ▼ (pass)                       ▼ (pass / raise)
    │
    ├── Rate limit check  (utils/rate_limiter.py)
    │
    ▼
POST /api/servers/{id}/start handler
    │
    ├── db_manager.get_server_config(id)   - - ►  DatabaseManager / InMemoryBackend
    │
    └── server_manager.start_server(id)   ───►   ServerManager
              │
              ├── subprocess.Popen(command, args, env)  ────►  MCP subprocess
              │
              └── db_manager.save_instance(...)         - - ►  DatabaseManager
```

### Startup sequence (server.py · main())

```
main(args)
  │
  ├─1─ Choose backend ──────────────────────────────────────────────────────────
  │       --in-memory  →  InMemoryBackend().connect()
  │       default      →  DatabaseManager(uri) → connect_with_retry(3 attempts)
  │                         attempt 1 ──►  MongoDB ping
  │                         attempt 2 (2s delay) ──►  MongoDB ping
  │                         attempt 3 (4s delay) ──►  MongoDB ping
  │                         failure + --require-persistence  →  RuntimeError (exit)
  │                         failure                           →  ephemeral mode
  │
  ├─2─ Create ServerManager(persistence)
  │
  ├─3─ Start background tasks
  │       server_manager.start_idle_cleanup_task()       - - ►  asyncio.Task (300s loop)
  │       MCPHealthMonitor(server_manager).start()       - - ►  asyncio.Task (30s loop)
  │
  ├─4─ create_app(db_manager, server_manager, ...)
  │       → registers CORSMiddleware
  │       → registers limit_request_size middleware
  │       → app.include_router(mgmt_router,      prefix="/api")
  │       → app.include_router(inspector_router, prefix="/api")
  │       → app.include_router(create_dynamic_router(server_manager))
  │       → setup_frontend_routes(app)
  │       → defines GET /health, GET /metrics, GET /
  │
  ├─5─ load_models_from_persistence(persistence)
  │       → list_llm_models() from backend
  │       → for each model: ReplicateClient(id, cfg).health_check()
  │           or launch_single_llm_model(id, cfg) for vllm/ollama/lmstudio
  │
  ├─6─ Register signal handlers  (SIGINT, SIGTERM, SIGHUP)
  │
  ├─7─ uvicorn.Server(Config(app, host, port)).serve()  - - ►  asyncio.Task
  │
  └─8─ await shutdown_event  →  graceful teardown
            stop MCPHealthMonitor
            stop idle cleanup task
            server_manager.shutdown_all() (10s timeout)
            persistence.disconnect()
```

## Layer Breakdown

### Entry / CLI Layer

The CLI entry point is `fluidmcp/cli/cli.py`. The `serve` subparser (registered as `serve_parser`) validates authentication flags and then calls `asyncio.run(server_main(args))`. The `server.py · main()` function is the true async entry point: it wires together the persistence backend, `ServerManager`, background tasks, and the FastAPI app, then runs uvicorn in a background asyncio task, blocking on a `shutdown_event`.

### FastAPI App Layer

`create_app()` constructs the FastAPI application and attaches all middleware and routers. Two security-oriented middleware layers are applied to every request before route handlers execute: `CORSMiddleware` enforces origin policy, and `limit_request_size` rejects bodies exceeding the configured size limit (default 10 MB, set via `MAX_REQUEST_SIZE_MB`). The `/health` endpoint is intentionally public and un-instrumented to avoid metric pollution from load-balancer probes.

> **Security note:** `limit_request_size` only enforces the body-size limit when a `Content-Length` header is present. Requests that use chunked transfer encoding (no `Content-Length`) bypass this check. For production deployments, configure a server-level limit in addition: Uvicorn `--limit-max-requests`, Nginx `client_max_body_size`, or an equivalent CDN/proxy setting.

### Auth (Cross-cutting)

`auth.py · verify_token()` is a FastAPI dependency injected with `Depends()`. It is stateless and reads two environment variables at call-time: `FMCP_SECURE_MODE` and `FMCP_BEARER_TOKEN`. When secure mode is off, it is a no-op. When on, it delegates to `_validate_bearer_token()` which performs a constant-time comparison (`secrets.compare_digest`) to prevent timing attacks.

### Routers Layer

Three routers are registered at app creation time:

- **mgmt_router** (`api/management.py`) — the primary API surface. Covers full server CRUD and lifecycle, SSE/message proxying, environment variable management, LLM model registration, OpenAI-compatible inference endpoints, and metrics endpoints.
- **inspector_router** (`api/inspector.py`) — tool inspection sessions; router-level `Depends(verify_token)` protects all routes.
- **Dynamic MCP proxy router** (created by `services/package_launcher.py · create_dynamic_router`) — mounted without a prefix; routes JSON-RPC calls to the correct running subprocess.

### Services Layer

`ServerManager` owns the subprocess lifecycle. It maintains an in-memory `processes` dict, acquires per-server async locks for concurrent safety, and surfaces `start_server / stop_server / restart_server / shutdown_all`. `MCPHealthMonitor` runs as a separate asyncio task, polling process state every 30 seconds and triggering auto-restarts with exponential backoff.

### Persistence Layer

Two backends implement the `PersistenceBackend` protocol:

- **DatabaseManager** — Motor-async MongoDB client. Handles server configs, instance records, logs (with a `LogBuffer` for write failures), LLM model configs, and crash events. Includes MongoDB injection sanitisation.
- **InMemoryBackend** — plain Python dicts and deques; zero network I/O; data is lost on restart; intended for development and CI.

### External Dependencies

- **MongoDB** — persistent store for server state and LLM model configs, accessed via the Motor async driver.
- **MCP subprocesses** — the actual MCP server processes (e.g., `npx -y @modelcontextprotocol/server-filesystem`) spawned by `ServerManager` via `subprocess.Popen`. Communication uses stdin/stdout (JSON-RPC) or SSE.
- **Replicate Cloud API** — HTTP polling client for cloud-based LLM and multimodal inference.
- **Sentry** — optional error tracking, enabled via `SENTRY_DSN` env var.

## Dependency Map

| Component | Imports / Calls | Purpose |
|---|---|---|
| `cli.py` | `server.py · main()` | Dispatch `fmcp serve` to async entry point |
| `server.py · main()` | `DatabaseManager`, `InMemoryBackend`, `ServerManager`, `MCPHealthMonitor`, `create_app()` | Orchestrate startup sequence |
| `server.py · create_app()` | `mgmt_router`, `inspector_router`, `create_dynamic_router`, `verify_token`, `CORSMiddleware` | Build FastAPI app |
| `auth.py · verify_token()` | `os.environ`, `secrets.compare_digest` | Stateless bearer token gate |
| `api/management.py` | `ServerManager` (via `request.app.state`), `DatabaseManager`, `ReplicateClient`, `llm_provider_registry`, `omni_adapter`, `rate_limiter` | MCP CRUD, lifecycle, inference |
| `api/inspector.py` | `verify_token` (router-level dep), MCP subprocess stdio | Interactive tool inspection sessions |
| `services/server_manager.py · ServerManager` | `DatabaseManager`, `package_launcher.initialize_mcp_server`, `MetricsCollector`, `HealthChecker` | Process lifecycle and state persistence |
| `services/server_manager.py · MCPHealthMonitor` | `ServerManager` | Background health polling and auto-restart |
| `repositories/database.py · DatabaseManager` | `motor.motor_asyncio.AsyncIOMotorClient`, `pymongo.errors`, `repositories.base.PersistenceBackend` | Async MongoDB persistence |
| `repositories/memory.py · InMemoryBackend` | `repositories.base.PersistenceBackend` | Ephemeral in-process persistence |

## Component Summary

| Component | File | Class / Function | Role |
|---|---|---|---|
| CLI serve dispatcher | `fluidmcp/cli/cli.py` | `serve_parser` + `args.command == "serve"` block | Parse flags, validate auth, call `asyncio.run(server_main(args))` |
| Async entry point | `fluidmcp/cli/server.py` | `main(args)` | Orchestrate persistence, services, app, uvicorn |
| App factory | `fluidmcp/cli/server.py` | `create_app()` | Build FastAPI app, attach middleware and routers |
| Lifespan context | `fluidmcp/cli/server.py` | `lifespan()` | Graceful DB disconnect on shutdown |
| Health endpoint | `fluidmcp/cli/server.py` | `GET /health` | Public status; pings MongoDB, counts models |
| Metrics endpoint | `fluidmcp/cli/server.py` | `GET /metrics` | Prometheus text format; auth-protected |
| CORS middleware | `fastapi.middleware.cors` | `CORSMiddleware` | Origin policy enforcement |
| Size limit middleware | `fluidmcp/cli/server.py` | `limit_request_size` | Reject oversized request bodies (HTTP 413) |
| Auth dependency | `fluidmcp/cli/auth.py` | `verify_token()` | Constant-time bearer token validation |
| Auth helper | `fluidmcp/cli/auth.py` | `_validate_bearer_token()` | Inner validation logic with timing-safe compare |
| Management router | `fluidmcp/cli/api/management.py` | `router` (mgmt_router) | Full MCP server CRUD, lifecycle, LLM, inference, metrics |
| Inspector router | `fluidmcp/cli/api/inspector.py` | `router` (inspector_router) | Interactive MCP tool inspection sessions |
| Dynamic proxy router | `fluidmcp/cli/services/package_launcher.py` | `create_dynamic_router()` | JSON-RPC proxy to MCP subprocesses |
| Server lifecycle | `fluidmcp/cli/services/server_manager.py` | `ServerManager` | Subprocess registry, start/stop/restart, idle cleanup |
| Health monitor | `fluidmcp/cli/services/server_manager.py` | `MCPHealthMonitor` | Background crash detection and auto-restart |
| MongoDB backend | `fluidmcp/cli/repositories/database.py` | `DatabaseManager` | Async Motor MongoDB persistence with injection sanitisation |
| In-memory backend | `fluidmcp/cli/repositories/memory.py` | `InMemoryBackend` | Ephemeral dict-based persistence for dev/test |
| Persistence interface | `fluidmcp/cli/repositories/base.py` | `PersistenceBackend` | Abstract protocol implemented by both backends |
| MongoDB retry | `fluidmcp/cli/server.py` | `connect_with_retry()` | 3-attempt exponential-backoff connection |
| Model loader | `fluidmcp/cli/server.py` | `load_models_from_persistence()` | Re-hydrate LLM models from DB on startup |
