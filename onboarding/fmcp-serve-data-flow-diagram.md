# FMCP Serve → Data Flow Diagram

> Shows how configuration and runtime data moves through the system from CLI input to running HTTP server, tracing transformations at each processing layer.

## Overview

This diagram traces the data pipeline for starting the FluidMCP backend server, showing how CLI arguments and environment variables transform through parsing, persistence setup, application building, and ultimately become HTTP endpoints with dynamic MCP management.

## Data Flow

```
┌─── INPUT ───────────────────────────────────────────────────────────────────┐
│                                                                              │
│  [ CLI Command ]                                                             │
│  fmcp serve --secure --mongodb-uri mongodb://localhost:27017 --port 8099    │
│  server.py · run()                                                           │
│                                                                              │
│                     ↓                                                        │
│                                                                              │
│  [ Parsed Args ]                                                             │
│  Namespace(                                                                  │
│    secure=True,                                                              │
│    token=None,                                                               │
│    mongodb_uri="mongodb://localhost:27017",                                  │
│    database="fluidmcp",                                                      │
│    port=8099,                                                                │
│    host="0.0.0.0",                                                           │
│    allowed_origins=None,                                                     │
│    require_persistence=False,                                                │
│    in_memory=False                                                           │
│  )                                                                           │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                     ↓
┌─── TOKEN GENERATION (IF SECURE MODE) ───────────────────────────────────────┐
│                                                                              │
│  < secure=True AND token=None? >                                            │
│                     │                                                        │
│                 [yes]                                                        │
│                     ↓                                                        │
│  [ Generate Token ]                                                          │
│  secrets.token_urlsafe(32)                                                   │
│  server.py:790                                                               │
│  → "Kx7j9mP2nQ5rT8wY1aB3cD4eF6gH0iL"  (example, 43 chars)                  │
│                     ↓                                                        │
│  [ Save to Secure File ]                                                     │
│  Path: ~/.fmcp/tokens/current_token.txt                                     │
│  Permissions: 0o600 (owner read/write only)                                 │
│  server.py:72-92                                                             │
│                     ↓                                                        │
│  [ Set Environment Variable ]                                                │
│  FMCP_BEARER_TOKEN="Kx7j9mP2nQ5rT8wY1aB3cD4eF6gH0iL"                        │
│  server.py:252                                                               │
│                     ↓                                                        │
│  [ Console Output ]                                                          │
│  Print to stdout (NOT logged for security)                                  │
│  server.py:797-805                                                           │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                     ↓
┌─── PERSISTENCE CONNECTION ──────────────────────────────────────────────────┐
│                                                                              │
│  [ MongoDB Configuration ]                                                   │
│  {                                                                           │
│    uri: "mongodb://localhost:27017",                                         │
│    database: "fluidmcp",                                                     │
│    timeouts: {server: 30000ms, connect: 10000ms, socket: 45000ms},          │
│    pool: {min: 10, max: 50},                                                 │
│    retryWrites: true,                                                        │
│    writeConcern: "majority"                                                  │
│  }                                                                           │
│  database.py:230-243                                                         │
│                     ↓                                                        │
│  [ Create AsyncIOMotorClient ]                                               │
│  motor.motor_asyncio.AsyncIOMotorClient(uri, **config)                      │
│  database.py:230                                                             │
│                     ↓                                                        │
│  [ Connection Retry Loop ]                                                   │
│  for attempt in [1, 2, 3]:                                                   │
│    try: client.admin.command('ping')                                         │
│    if success: break                                                         │
│    else: wait exponential_backoff(2^attempt)                                 │
│  server.py:404-447                                                           │
│                     ↓                                                        │
│  < Connection successful? >                                                  │
│         │                                                                    │
│     [yes] ──► [ Database Handle ]                                            │
│         │     db = client["fluidmcp"]                                        │
│         │     database.py:255                                                │
│         │              ↓                                                     │
│         │     [ Create Indexes ]                                             │
│         │     • fluidmcp_servers.id (unique)                                 │
│         │     • fluidmcp_server_instances.server_id                          │
│         │     • fluidmcp_server_logs (compound: server_name, timestamp)      │
│         │     • fluidmcp_llm_models.model_id (unique)                        │
│         │     database.py:322-376                                            │
│         │              ↓                                                     │
│         │     [ DatabaseManager Instance ]                                   │
│         │     {client, db, _change_streams_supported, _log_buffer}           │
│         │                                                                    │
│     [no] ──► < --require-persistence? >                                      │
│                  │                                                           │
│              [yes] ──► RuntimeError: "MongoDB required but unavailable"      │
│                  │     Exit with error                                       │
│              [no]                                                            │
│                  ↓                                                           │
│         [ InMemoryBackend ]                                                  │
│         memory.py:InMemoryBackend()                                          │
│         {_servers: {}, _instances: {}, _logs: [], _models: {}}               │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                     ↓
┌─── SERVER MANAGER INITIALIZATION ───────────────────────────────────────────┐
│                                                                              │
│  [ ServerManager Creation ]                                                  │
│  ServerManager(db_manager)                                                   │
│  server_manager.py:28-65                                                     │
│                     ↓                                                        │
│  [ Initial State ]                                                           │
│  {                                                                           │
│    db: db_manager,                                                           │
│    processes: {},           // Empty: no MCP servers loaded                 │
│    configs: {},             // Empty: no configurations                     │
│    start_times: {},         // Empty: no uptime tracking yet                │
│    _operation_locks: {},    // Empty: no active operations                  │
│    health_checker: HealthChecker(),                                          │
│    idle_timeout_seconds: 3600,  // 1 hour (from FMCP_IDLE_TIMEOUT)          │
│    cleanup_interval_seconds: 300  // 5 minutes                              │
│  }                                                                           │
│                     ↓                                                        │
│  [ Start Background Task ]                                                   │
│  _cleanup_task = asyncio.create_task(_idle_cleanup_loop())                  │
│  server_manager.py:1126-1136                                                 │
│  • Runs every 5 minutes                                                      │
│  • Stops servers idle > 1 hour                                               │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                     ↓
┌─── FASTAPI APPLICATION BUILD ───────────────────────────────────────────────┐
│                                                                              │
│  [ Application Configuration ]                                               │
│  {                                                                           │
│    db_manager: DatabaseManager,                                              │
│    server_manager: ServerManager,                                            │
│    secure_mode: True,                                                        │
│    token: "Kx7j9mP2nQ5rT8wY1aB3cD4eF6gH0iL",                                │
│    allowed_origins: ["http://localhost:*", "http://127.0.0.1:*"],           │
│    port: 8099                                                                │
│  }                                                                           │
│  server.py:118-137                                                           │
│                     ↓                                                        │
│  [ FastAPI Instance ]                                                        │
│  app = FastAPI(                                                              │
│    title="FluidMCP Gateway",                                                 │
│    description="Unified gateway for MCP servers with dynamic management",   │
│    version="2.0.0",                                                          │
│    lifespan=lifespan  // Startup/shutdown hooks                             │
│  )                                                                           │
│  server.py:132-137                                                           │
│                     ↓                                                        │
│  [ Middleware Stack ]                                                        │
│  1. CORSMiddleware                                                           │
│     allow_origins=["http://localhost:*", "http://127.0.0.1:*"]              │
│     allow_credentials=True                                                   │
│     allow_methods=["*"]                                                      │
│     allow_headers=["*"]                                                      │
│     server.py:158-164                                                        │
│                                                                              │
│  2. Request Size Limiter                                                     │
│     max_size = 10 * 1024 * 1024  // 10MB                                    │
│     Check Content-Length header                                             │
│     Raise 413 if > max_size                                                  │
│     server.py:184-227                                                        │
│                                                                              │
│  3. Bearer Token Auth (if secure mode)                                      │
│     Validate Authorization: Bearer <token>                                   │
│     Compare with FMCP_BEARER_TOKEN env var                                   │
│     Raise 401 if invalid                                                     │
│     auth.py:verify_token()                                                   │
│                     ↓                                                        │
│  [ Store in app.state ]                                                      │
│  app.state.persistence = db_manager                                          │
│  app.state.db_manager = db_manager                                           │
│  app.state.server_manager = server_manager                                   │
│  server.py:140, 236-238                                                      │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                     ↓
┌─── API ROUTING CONFIGURATION ───────────────────────────────────────────────┐
│                                                                              │
│  [ Management API Router ]                                                   │
│  router = APIRouter(prefix="/api", tags=["management"])                     │
│  api/management.py                                                           │
│                     ↓                                                        │
│  [ Management Endpoints ]                                                    │
│  POST   /api/servers                     → Create server config             │
│  GET    /api/servers                     → List all servers                 │
│  GET    /api/servers/{id}                → Get server details               │
│  PUT    /api/servers/{id}                → Update server config             │
│  DELETE /api/servers/{id}                → Delete server config             │
│  POST   /api/servers/{id}/start          → Start MCP server                 │
│  POST   /api/servers/{id}/stop           → Stop MCP server                  │
│  POST   /api/servers/{id}/restart        → Restart MCP server               │
│  GET    /api/servers/{id}/status         → Get server status                │
│  GET    /api/servers/{id}/logs           → Get server logs                  │
│  GET    /api/servers/{id}/env            → Get environment variables        │
│  PUT    /api/servers/{id}/env            → Update environment variables     │
│  app.include_router(mgmt_router)                                            │
│  server.py:257                                                               │
│                     ↓                                                        │
│  [ Dynamic MCP Router ]                                                      │
│  mcp_router = create_dynamic_router(server_manager)                         │
│  package_launcher.py:create_dynamic_router()                                │
│                     ↓                                                        │
│  [ Dynamic MCP Endpoints ]                                                   │
│  POST   /{server_name}/mcp               → JSON-RPC proxy to MCP server     │
│  POST   /{server_name}/sse               → Server-Sent Events stream        │
│  GET    /{server_name}/mcp/tools/list    → List available tools             │
│  POST   /{server_name}/mcp/tools/call    → Execute tool                     │
│  app.include_router(mcp_router)                                             │
│  server.py:261-262                                                           │
│                     ↓                                                        │
│  [ Core Endpoints ]                                                          │
│  GET    /                                 → API info                         │
│  GET    /health                           → Health check                     │
│  GET    /metrics                          → Prometheus metrics               │
│  server.py:273-399                                                           │
│                     ↓                                                        │
│  [ Frontend Routes ]                                                         │
│  setup_frontend_routes(app, host, port)                                     │
│  • Mounts React static files at /                                           │
│  • Serves index.html for SPA routing                                        │
│  frontend_utils.py:setup_frontend_routes()                                  │
│  server.py:266                                                               │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                     ↓
┌─── MODEL LOADING (IF MONGODB CONNECTED) ────────────────────────────────────┐
│                                                                              │
│  [ Query LLM Models ]                                                        │
│  models = await db_manager.list_llm_models()                                │
│  server.py:469                                                               │
│                     ↓                                                        │
│  [ Model Documents ]                                                         │
│  [                                                                           │
│    {                                                                         │
│      model_id: "llama-2-70b",                                                │
│      type: "replicate",                                                      │
│      model: "meta/llama-2-70b-chat",                                         │
│      api_key: "${REPLICATE_API_TOKEN}",                                      │
│      default_params: {temperature: 0.7, max_tokens: 1000},                  │
│      timeout: 120,                                                           │
│      max_retries: 3                                                          │
│    },                                                                        │
│    {                                                                         │
│      model_id: "vllm-opt",                                                   │
│      type: "vllm",                                                           │
│      command: "vllm",                                                        │
│      args: ["serve", "facebook/opt-125m", "--port", "8001"],                │
│      endpoints: {base_url: "http://localhost:8001/v1"},                     │
│      restart_policy: "on-failure",                                           │
│      max_restarts: 3                                                         │
│    }                                                                         │
│  ]                                                                           │
│                     ↓                                                        │
│  For each model:                                                             │
│    IF type == "replicate":                                                   │
│      1. ReplicateClient(model_id, config)                                    │
│      2. Health check: GET https://api.replicate.com/v1/models/...           │
│      3. IF success:                                                          │
│           _replicate_clients[model_id] = client                              │
│           _llm_models_config[model_id] = config                              │
│      server.py:496-534                                                       │
│                                                                              │
│    IF type in ["vllm", "ollama", "lmstudio"]:                               │
│      1. launch_single_llm_model(model_id, config)                           │
│      2. subprocess.Popen([command, args], ...)                              │
│      3. IF success:                                                          │
│           register_llm_process(model_id, process)                           │
│           _llm_models_config[model_id] = config                              │
│      server.py:538-562                                                       │
│                     ↓                                                        │
│  [ Loaded Models Registry ]                                                  │
│  _replicate_clients = {"llama-2-70b": ReplicateClient(...)}                 │
│  _llm_models_config = {                                                      │
│    "llama-2-70b": {type: "replicate", ...},                                  │
│    "vllm-opt": {type: "vllm", ...}                                           │
│  }                                                                           │
│  get_llm_processes() = {"vllm-opt": LLMProcess(...)}                        │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                     ↓
┌─── SERVER STARTUP ──────────────────────────────────────────────────────────┐
│                                                                              │
│  [ Uvicorn Configuration ]                                                   │
│  config = Config(                                                            │
│    app=app,                                                                  │
│    host="0.0.0.0",                                                           │
│    port=8099,                                                                │
│    loop="asyncio",                                                           │
│    log_level="info"                                                          │
│  )                                                                           │
│  server.py:675-683                                                           │
│                     ↓                                                        │
│  [ Start HTTP Server ]                                                       │
│  server = Server(config)                                                     │
│  await server.serve()                                                        │
│  server.py:684-691                                                           │
│                     ↓                                                        │
│  [ Bind to Port ]                                                            │
│  Listening on: 0.0.0.0:8099                                                  │
│  • Main thread: blocked in await shutdown_event.wait()                      │
│  • Background tasks running: idle cleanup, log retry                        │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                     ↓
┌─── OUTPUT ──────────────────────────────────────────────────────────────────┐
│                                                                              │
│  [ Running HTTP Server ]                                                     │
│  http://0.0.0.0:8099                                                         │
│                                                                              │
│  Available endpoints:                                                        │
│    GET  /                            → API info                              │
│    GET  /docs                        → Swagger UI                            │
│    GET  /health                      → Health check                          │
│    GET  /metrics                     → Prometheus metrics                    │
│    POST /api/servers                 → Create MCP server config              │
│    POST /api/servers/{id}/start      → Start MCP server                      │
│    POST /{server}/mcp                → JSON-RPC proxy                        │
│    GET  /{server}/mcp/tools/list     → Tool discovery                        │
│                                                                              │
│  Server state:                                                               │
│    • NO MCP servers running (empty processes: {})                           │
│    • Bearer token authentication enabled                                     │
│    • MongoDB persistence active                                              │
│    • 2 LLM models loaded (llama-2-70b, vllm-opt)                            │
│    • Idle cleanup task running (checks every 5min)                          │
│                                                                              │
│  User can now:                                                               │
│    1. Add server configs via POST /api/servers                              │
│    2. Start servers via POST /api/servers/{id}/start                        │
│    3. Make MCP requests via POST /{server}/mcp                              │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Data Transformations

| Input | Transformation | Output | Location |
|-------|---------------|--------|----------|
| CLI args string | argparse.parse_args() | Namespace object | server.py:782 |
| Secure mode flag | secrets.token_urlsafe(32) | 43-char bearer token | server.py:790 |
| Bearer token | save_token_to_file() | ~/.fmcp/tokens/current_token.txt (0o600) | server.py:72-92 |
| MongoDB URI | AsyncIOMotorClient() | Motor client instance | database.py:230 |
| Connection retry | Exponential backoff (2^attempt) | Connected or fallback | server.py:420-433 |
| Database name | client[database_name] | Database handle | database.py:255 |
| Index definitions | create_index() | MongoDB indexes | database.py:339-352 |
| db_manager | ServerManager(db_manager) | ServerManager instance | server_manager.py:28 |
| Managers + config | create_app() | FastAPI application | server.py:118-401 |
| Allowed origins | CORSMiddleware() | CORS headers in responses | server.py:158-164 |
| Max request size | limit_request_size() | 413 if > 10MB | server.py:184-227 |
| Bearer token | verify_token() | 401 if invalid | auth.py:verify_token() |
| Management router | app.include_router() | Mounted /api/* endpoints | server.py:257 |
| Dynamic router | create_dynamic_router() | Mounted /{server}/* endpoints | server.py:261-262 |
| Static files | setup_frontend_routes() | Served React app at / | frontend_utils.py |
| LLM model docs | ReplicateClient() | Initialized API clients | server.py:508 |
| vLLM config | subprocess.Popen() | Running vLLM process | server.py:549 |
| FastAPI app | uvicorn.run() | HTTP server on port 8099 | server.py:691 |

## Data Flow Summary

| Step | Component | File | Function | Data In | Data Out |
|------|-----------|------|----------|---------|----------|
| 1 | CLI Parser | server.py | run() → argparse | CLI args string | Namespace object |
| 2 | Token Generator | server.py | save_token_to_file() | None (if missing) | Bearer token string |
| 3 | Token Storage | server.py | save_token_to_file() | Token string | File path + env var |
| 4 | MongoDB Client | database.py | DatabaseManager() | URI + config | Motor client |
| 5 | Connection | database.py | connect() | Client | Connected client |
| 6 | Retry Logic | server.py | connect_with_retry() | Client + retries | Success/failure |
| 7 | Index Creation | database.py | init_db() | Database handle | Indexes |
| 8 | Server Manager | server_manager.py | ServerManager() | db_manager | Manager instance |
| 9 | Idle Cleanup | server_manager.py | start_idle_cleanup_task() | Manager | Background task |
| 10 | FastAPI App | server.py | create_app() | Managers + config | FastAPI app |
| 11 | CORS Setup | server.py | add_middleware() | Allowed origins | Middleware |
| 12 | Size Limiter | server.py | @app.middleware() | Max size (10MB) | Middleware |
| 13 | Token Auth | auth.py | verify_token() | Bearer token | 200/401 |
| 14 | Management API | api/management.py | router | – | API endpoints |
| 15 | Dynamic Router | package_launcher.py | create_dynamic_router() | server_manager | MCP endpoints |
| 16 | Frontend | frontend_utils.py | setup_frontend_routes() | Static files | Served UI |
| 17 | Model Query | database.py | list_llm_models() | Query | Model docs |
| 18 | Replicate Init | server.py | ReplicateClient() | Model config | API client |
| 19 | vLLM Launch | server.py | launch_single_llm_model() | Command + args | Process |
| 20 | Uvicorn Config | server.py | Config() | App + host/port | Config object |
| 21 | Server Start | server.py | Server.serve() | Config | HTTP server |

## Environment Variables

| Variable | Source | Transformation | Usage |
|----------|--------|---------------|-------|
| FMCP_BEARER_TOKEN | CLI/env/generated | Set by server.py:252 | Bearer auth validation |
| FMCP_SECURE_MODE | Set by app | "true" string | Middleware flag |
| MONGODB_URI | CLI/env/default | Parsed by Motor | Database connection |
| PORT | Env (Railway) | int() → default 8099 | Uvicorn binding |
| FMCP_ALLOWED_ORIGINS | CLI/env | Split by comma | CORS configuration |
| SENTRY_DSN | Env | sentry_sdk.init() | Error tracking |
| FMCP_IDLE_TIMEOUT | Env | int() → default 3600 | Idle cleanup |
| MAX_REQUEST_SIZE_MB | Env | int() → default 10 | Request limiter |
| REPLICATE_API_TOKEN | Env | Passed to client | Replicate auth |

## MongoDB Collections & Schema

| Collection | Documents | Transformation |
|-----------|-----------|---------------|
| fluidmcp_servers | Server configs | save_server_config() → {id, name, mcp_config, enabled, ...} |
| fluidmcp_server_instances | Runtime state | save_instance_state() → {server_id, state, pid, start_time, ...} |
| fluidmcp_server_logs | Process logs | save_log_entry() → {server_name, timestamp, stream, content} |
| fluidmcp_llm_models | LLM configs | save_llm_model() → {model_id, type, model, api_key, ...} |
| fluidmcp_llm_model_versions | Version history | update_llm_model() → {model_id, version, archived_at, ...} |

## Runtime State Registries

| Registry | Storage | Access | Transformation |
|----------|---------|--------|---------------|
| MCP Processes | ServerManager.processes | server_id → Popen | start_server() → {id: process} |
| MCP Configs | ServerManager.configs | server_id → dict | load from DB → {id: config} |
| MCP Start Times | ServerManager.start_times | server_id → float | time.monotonic() → {id: timestamp} |
| LLM Clients | _replicate_clients | model_id → client | ReplicateClient() → {id: client} |
| LLM Models | _llm_models_config | model_id → config | load from DB → {id: config} |
| LLM Processes | _llm_processes | model_id → process | launch_single_llm_model() → {id: process} |

## Request Flow Example (After Startup)

```
HTTP Request:
  POST /api/servers
  Authorization: Bearer Kx7j9mP2nQ5rT8wY1aB3cD4eF6gH0iL
  Body: {server_id: "filesystem", config: {...}}
    ↓
CORS Check:
  Origin: http://localhost:3000
  → Allowed (in allow_origins list)
    ↓
Size Check:
  Content-Length: 342 bytes
  → Allowed (< 10MB)
    ↓
Auth Check:
  Bearer token: Kx7j9mP2nQ5rT8wY1aB3cD4eF6gH0iL
  FMCP_BEARER_TOKEN: Kx7j9mP2nQ5rT8wY1aB3cD4eF6gH0iL
  → Match: Authorized
    ↓
Route Handler:
  Management API: create_server()
  → db_manager.save_server_config(config)
  → MongoDB: INSERT fluidmcp_servers
    ↓
Response:
  201 Created
  Body: {id: "filesystem", name: "Filesystem", status: "stopped", ...}
```

## Notes

- **No MCP Servers at Startup**: Unlike `fmcp run`, serve mode starts with empty `processes: {}`
- **Token Persistence Critical**: Railway containers restart frequently, token must be in env to survive
- **Exponential Backoff**: MongoDB retry delays: 2s, 4s, 8s (total 14s + 3 connection attempts)
- **Idle Cleanup**: Background task runs every 5 minutes, stops servers idle > 1 hour
- **CORS Security**: Default allows localhost only, wildcard requires explicit flag
- **Request Limit**: 10MB body size checked via Content-Length (note: chunked encoding bypasses)
- **Model Loading**: Only happens if MongoDB connected, skipped if in-memory mode
- **Health Check**: Returns DB status + model count (used by Railway load balancer)
- **Metrics Endpoint**: Prometheus format with system metrics (CPU, memory, GPU)
