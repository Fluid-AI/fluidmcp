# FMCP Serve → Sequence Diagram

> Step-by-step interactions between actors showing who calls who, in what order, with what data during `fmcp serve` startup.

## Participants

| Actor | File | Key Function |
|-------|------|-------------|
| User | – | CLI caller |
| CLI | server.py | run(), main() |
| DatabaseManager | repositories/database.py | connect(), init_db() |
| MongoDB | External | Database server |
| ServerManager | services/server_manager.py | ServerManager() |
| FastAPI | server.py | create_app() |
| ManagementAPI | api/management.py | router |
| FrontendUtils | services/frontend_utils.py | setup_frontend_routes() |
| Uvicorn | External | HTTP server |

## Sequence

```
     User                 CLI              DatabaseManager      MongoDB        ServerManager
                       server.py           database.py        (external)       server_manager.py
                       run() → main()
        │                  │                      │                │                 │
   1.   │──fmcp serve --secure --mongodb-uri mongodb://localhost ──►│                │
        │  --port 8099       │                      │                │                 │
        │                  │                      │                │                 │
   2.   │                  │──parse_args()────────►│                │                 │
        │                  │  (argparse)           │                │                 │
        │                  │                      │                │                 │
   3.   │                  │◄─ args ──────────────│                │                 │
        │                  │  {secure: True,      │                │                 │
        │                  │   mongodb_uri: ...,  │                │                 │
        │                  │   port: 8099}        │                │                 │
        │                  │                      │                │                 │
   4.   │                  │──IF secure AND no token:─────────────►│                 │
        │                  │  Generate token      │                │                 │
        │                  │  secrets.token_urlsafe(32)            │                 │
        │                  │                      │                │                 │
   5.   │                  │──save_token_to_file()─────────────────►│                │
        │                  │  ~/.fmcp/tokens/     │                │                 │
        │                  │  current_token.txt   │                │                 │
        │                  │                      │                │                 │
   6.   │◄───Token: abc123... (printed to console, NOT logged)────│                 │
        │                  │                      │                │                 │
   7.   │                  │──Choose persistence backend──────────►│                 │
        │                  │  (MongoDB or in-memory)│                │                 │
        │                  │                      │                │                 │
   8.   │                  │──DatabaseManager()───►│                │                 │
        │                  │  (mongodb_uri,       │                │                 │
        │                  │   database="fluidmcp")│                │                 │
        │                  │                      │                │                 │
   9.   │                  │                      │──connect()─────►│                 │
        │                  │                      │  AsyncIOMotorClient()            │
        │                  │                      │  (with timeouts, pool config)    │
        │                  │                      │                │                 │
  10.   │                  │                      │──ping()────────►│                 │
        │                  │                      │  client.admin.command('ping')    │
        │                  │                      │                │                 │
  11.   │                  │                      │◄─ pong ─────────│                 │
        │                  │                      │  (success)     │                 │
        │                  │                      │                │                 │
  12.   │                  │                      │──init_db()─────►│                 │
        │                  │                      │  Create indexes│                 │
        │                  │                      │                │                 │
  13.   │                  │                      │◄─ indexes created──              │
        │                  │                      │                │                 │
  14.   │                  │◄─ db_manager ─────────│                │                 │
        │                  │  (connected)         │                │                 │
        │                  │                      │                │                 │
  15.   │                  │──init_sentry()───────►│                │                 │
        │                  │  (if SENTRY_DSN set) │                │                 │
        │                  │                      │                │                 │
  16.   │                  │──ServerManager()─────────────────────►│                 │
        │                  │  (db_manager)        │                │                 │
        │                  │                      │                │                 │
  17.   │                  │                      │                │──Initialize────►│
        │                  │                      │                │  • processes = {}│
        │                  │                      │                │  • configs = {}  │
        │                  │                      │                │  • locks = {}    │
        │                  │                      │                │                 │
  18.   │                  │                      │                │──start_idle_    │
        │                  │                      │                │  cleanup_task() │
        │                  │                      │                │  (background)   │
        │                  │                      │                │                 │
  19.   │                  │◄─ server_manager ────────────────────│                 │
        │                  │                      │                │                 │


     User                 CLI              FastAPI          ManagementAPI      FrontendUtils    Uvicorn
                       server.py                         management.py       frontend_utils.py (server)
                       main()
        │                  │                      │                │                 │           │
  20.   │                  │──create_app()────────►│                │                 │           │
        │                  │  (db_manager,        │                │                 │           │
        │                  │   server_manager,    │                │                 │           │
        │                  │   secure_mode=True,  │                │                 │           │
        │                  │   token=...,         │                │                 │           │
        │                  │   allowed_origins=None,│               │                 │           │
        │                  │   port=8099)         │                │                 │           │
        │                  │                      │                │                 │           │
  21.   │                  │                      │──FastAPI()─────►│                │           │
        │                  │                      │  (title, desc, │                │           │
        │                  │                      │   version,     │                │           │
        │                  │                      │   lifespan)    │                │           │
        │                  │                      │                │                 │           │
  22.   │                  │                      │──Add CORS middleware────────────►│           │
        │                  │                      │  CORSMiddleware│                │           │
        │                  │                      │  (allow_origins=["localhost:*"])│           │
        │                  │                      │                │                 │           │
  23.   │                  │                      │──Add request size limiter───────►│           │
        │                  │                      │  @app.middleware("http")        │           │
        │                  │                      │  limit_request_size()           │           │
        │                  │                      │  (max 10MB)    │                 │           │
        │                  │                      │                │                 │           │
  24.   │                  │                      │──Store managers in app.state───►│           │
        │                  │                      │  app.state.db_manager           │           │
        │                  │                      │  app.state.server_manager       │           │
        │                  │                      │                │                 │           │
  25.   │                  │                      │──IF secure_mode:───────────────►│           │
        │                  │                      │  os.environ["FMCP_BEARER_TOKEN"]│           │
        │                  │                      │  os.environ["FMCP_SECURE_MODE"] │           │
        │                  │                      │                │                 │           │
  26.   │                  │                      │──Include Management API─────────►│           │
        │                  │                      │  app.include_router(mgmt_router)│           │
        │                  │                      │  prefix="/api" │                 │           │
        │                  │                      │                │                 │           │
  27.   │                  │                      │──Create Dynamic MCP Router──────►│           │
        │                  │                      │  create_dynamic_router()        │           │
        │                  │                      │  (server_manager)│               │           │
        │                  │                      │                │                 │           │
  28.   │                  │                      │──Include Dynamic Router─────────►│           │
        │                  │                      │  app.include_router(mcp_router) │           │
        │                  │                      │  (no prefix)   │                 │           │
        │                  │                      │                │                 │           │
  29.   │                  │                      │──setup_frontend_routes()────────►│           │
        │                  │                      │  (app, host, port)│              │           │
        │                  │                      │                │                 │           │
  30.   │                  │                      │                │──Mount static───►│           │
        │                  │                      │                │  files at /     │           │
        │                  │                      │                │  (React app)    │           │
        │                  │                      │                │                 │           │
  31.   │                  │                      │──Add health endpoint────────────►│           │
        │                  │                      │  @app.get("/health")            │           │
        │                  │                      │  health_check()│                 │           │
        │                  │                      │                │                 │           │
  32.   │                  │                      │──Add metrics endpoint───────────►│           │
        │                  │                      │  @app.get("/metrics")           │           │
        │                  │                      │  metrics()     │                 │           │
        │                  │                      │                │                 │           │
  33.   │                  │                      │──Add root endpoint──────────────►│           │
        │                  │                      │  @app.get("/") │                 │           │
        │                  │                      │  root()        │                 │           │
        │                  │                      │                │                 │           │
  34.   │                  │◄─ app ───────────────│                │                 │           │
        │                  │  (FastAPI ready)     │                │                 │           │
        │                  │                      │                │                 │           │
  35.   │                  │──load_models_from_persistence()───────►│                │           │
        │                  │  (db_manager)        │                │                 │           │
        │                  │                      │                │                 │           │
  36.   │                  │                      │──list_llm_models()──────────────►│           │
        │                  │                      │                │                 │           │
  37.   │                  │                      │◄─ models ───────│                │           │
        │                  │                      │  [{model_id, type, ...}, ...]   │           │
        │                  │                      │                │                 │           │
  38.   │                  │──For each model: Initialize client────►│                │           │
        │                  │  (Replicate, vLLM, Ollama, ...)       │                 │           │
        │                  │                      │                │                 │           │
  39.   │                  │◄─ loaded_count ──────│                │                 │           │
        │                  │  (e.g., 3 models)    │                │                 │           │
        │                  │                      │                │                 │           │
  40.   │                  │──Setup signal handlers────────────────►│                │           │
        │                  │  signal.signal(SIGINT, signal_handler)│                 │           │
        │                  │  signal.signal(SIGTERM, ...)          │                 │           │
        │                  │                      │                │                 │           │
  41.   │                  │──Config(app, host, port, ...)─────────────────────────►│           │
        │                  │  (uvicorn config)    │                │                 │           │
        │                  │                      │                │                 │           │
  42.   │                  │──Server(config)──────────────────────────────────────────►          │
        │                  │                      │                │                 │           │
  43.   │                  │──server.serve()──────────────────────────────────────────►          │
        │                  │  (start async task)  │                │                 │           │
        │                  │                      │                │                 │           │
  44.   │                  │                      │                │                 │──HTTP server│
        │                  │                      │                │                 │  starts   │
        │                  │                      │                │                 │  (0.0.0.0:│
        │                  │                      │                │                 │   8099)   │
        │                  │                      │                │                 │           │
  45.   │◄───Server ready: http://0.0.0.0:8099───────────────────────────────────────────────────│
        │                  │  Swagger UI: /docs   │                │                 │           │
        │                  │  Health: /health     │                │                 │           │
        │                  │  NO MCP servers loaded (added dynamically via API)                  │
        │                  │                      │                │                 │           │
  46.   │                  │──await shutdown_event.wait()──────────►│                │           │
        │                  │  (blocks until signal received)        │                 │           │
        │                  │                      │                │                 │           │
```

## Notes

- **Steps 1-19**: Configuration and persistence setup
- **Steps 20-34**: FastAPI application creation with middleware and routes
- **Steps 35-39**: LLM model loading from persistence (if MongoDB connected)
- **Steps 40-46**: Server startup and readiness
- **Parallel execution**: Background tasks (idle cleanup, log retry) run concurrently after step 18
- **Synchronous startup**: All setup steps complete before uvicorn binds to port
- **Port binding**: Step 43 binds to port 8099 (or $PORT env var for Railway)
- **No MCP servers**: Unlike `fmcp run`, serve mode starts with empty process registry

## Interaction Summary

| Step | From | To | Call | Returns |
|------|------|----|------|---------|
| 1 | User | CLI | fmcp serve command | – |
| 2-3 | CLI | argparse | parse_args() | Parsed args dict |
| 4-5 | CLI | File | save_token_to_file() | Token file path |
| 8 | CLI | DatabaseManager | DatabaseManager() | db_manager instance |
| 9-11 | DatabaseManager | MongoDB | connect() + ping() | Connection success |
| 12-13 | DatabaseManager | MongoDB | init_db() | Indexes created |
| 16-19 | CLI | ServerManager | ServerManager() | server_manager instance |
| 20-34 | CLI | FastAPI | create_app() | FastAPI app |
| 21 | FastAPI | FastAPI | FastAPI() | App instance |
| 22 | FastAPI | CORS | add_middleware() | – |
| 23 | FastAPI | Middleware | @app.middleware() | – |
| 26 | FastAPI | ManagementAPI | include_router() | – |
| 27-28 | FastAPI | DynamicRouter | create_dynamic_router() + include | – |
| 29-30 | FastAPI | FrontendUtils | setup_frontend_routes() | – |
| 31-33 | FastAPI | Endpoints | @app.get() decorators | – |
| 35-39 | CLI | DatabaseManager | load_models_from_persistence() | Loaded count |
| 40 | CLI | signal | signal.signal() | – |
| 41-43 | CLI | Uvicorn | Config() + Server() + serve() | – |
| 44 | Uvicorn | Network | Bind to port | – |
| 45 | Uvicorn | User | Server URL | – |

## Graceful Shutdown Sequence

```
     User                 CLI              ServerManager    DatabaseManager    Uvicorn
                       server.py           server_manager.py database.py       (server)
        │                  │                      │                │                 │
   1.   │──SIGINT (Ctrl+C)────────────────────────►│                │                 │
        │                  │                      │                │                 │
   2.   │                  │──shutdown_event.set()────────────────►│                │
        │                  │                      │                │                 │
   3.   │                  │──stop_idle_cleanup_task()────────────►│                │
        │                  │                      │                │                 │
   4.   │                  │◄─ task stopped ──────│                │                 │
        │                  │                      │                │                 │
   5.   │                  │──shutdown_all()──────►│                │                 │
        │                  │                      │──For each server:───────────────►│
        │                  │                      │  stop_server() │                 │
        │                  │                      │  (10s timeout) │                 │
        │                  │                      │                │                 │
   6.   │                  │◄─ all stopped ───────│                │                 │
        │                  │                      │                │                 │
   7.   │                  │──disconnect()────────────────────────►│                 │
        │                  │                      │                │──Close MongoDB  │
        │                  │                      │                │  connection     │
        │                  │                      │                │                 │
   8.   │                  │◄─ disconnected ──────│                │                 │
        │                  │                      │                │                 │
   9.   │◄───Backend server stopped successfully───────────────────────────────────────
        │                  │                      │                │                 │
```

## MongoDB Connection Retry Sequence

```
     CLI                  DatabaseManager      MongoDB
   server.py               database.py        (external)
        │                      │                    │
   1.   │──connect_with_retry()────────────────────►│
        │  (max_retries=3)     │                    │
        │                      │                    │
   2.   │                      │──Attempt 1─────────►│
        │                      │  ping()            │
        │                      │                    │
   3.   │                      │◄─ timeout ──────────│
        │                      │  (failed)          │
        │                      │                    │
   4.   │                      │──Wait 2s (2^1)─────►│
        │                      │  asyncio.sleep(2)  │
        │                      │                    │
   5.   │                      │──Attempt 2─────────►│
        │                      │  ping()            │
        │                      │                    │
   6.   │                      │◄─ timeout ──────────│
        │                      │  (failed)          │
        │                      │                    │
   7.   │                      │──Wait 4s (2^2)─────►│
        │                      │  asyncio.sleep(4)  │
        │                      │                    │
   8.   │                      │──Attempt 3─────────►│
        │                      │  ping()            │
        │                      │                    │
   9.   │                      │◄─ pong ─────────────│
        │                      │  (success!)        │
        │                      │                    │
  10.   │◄─ True (connected)───│                    │
        │                      │                    │
```

## API Request Sequence (After Startup)

```
     User                 Uvicorn          ManagementAPI     ServerManager      MCP Process
                         (server)         management.py      server_manager.py   (subprocess)
        │                      │                │                 │                    │
   1.   │──POST /api/servers───────────────────►│                 │                    │
        │  {server_id, config} │                │                 │                    │
        │  Authorization: Bearer ...            │                 │                    │
        │                      │                │                 │                    │
   2.   │                      │                │──verify_token()─►│                   │
        │                      │                │  (middleware)   │                    │
        │                      │                │                 │                    │
   3.   │                      │                │──save_server_   │                    │
        │                      │                │  config()       │                    │
        │                      │                │  (to MongoDB)   │                    │
        │                      │                │                 │                    │
   4.   │◄─ 201 Created ────────────────────────│                 │                    │
        │                      │                │                 │                    │
   5.   │──POST /api/servers/{id}/start─────────►│                │                    │
        │  Authorization: Bearer ...            │                 │                    │
        │                      │                │                 │                    │
   6.   │                      │                │──start_server()─►│                   │
        │                      │                │  (id, config)   │                    │
        │                      │                │                 │                    │
   7.   │                      │                │                 │──subprocess.Popen()─►
        │                      │                │                 │  [command, args]  │
        │                      │                │                 │  stdin/stdout     │
        │                      │                │                 │                    │
   8.   │                      │                │                 │──initialize_mcp_   │
        │                      │                │                 │  server()          │
        │                      │                │                 │  (JSON-RPC        │
        │                      │                │                 │   handshake)      │
        │                      │                │                 │                    │
   9.   │◄─ 200 OK {status: "running"} ────────│                 │                    │
        │                      │                │                 │                    │
  10.   │──POST /{server}/mcp──────────────────►│                 │                    │
        │  {jsonrpc, method, params}            │                 │                    │
        │                      │                │                 │                    │
  11.   │                      │──Dynamic Router────────────────►│                    │
        │                      │  (routes to process)            │                    │
        │                      │                │                 │                    │
  12.   │                      │                │                 │──stdin.write()─────►
        │                      │                │                 │  JSON-RPC request │
        │                      │                │                 │                    │
  13.   │                      │                │                 │◄─stdout.readline()─│
        │                      │                │                 │  JSON-RPC response│
        │                      │                │                 │                    │
  14.   │◄─ 200 OK {result} ──────────────────────────────────────│                   │
        │                      │                │                 │                    │
```
