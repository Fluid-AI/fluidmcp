# FMCP Serve → Feature Flow Diagram

> Complete end-to-end flow showing how `fmcp serve` starts the standalone API server, including all decision points and error paths.

## Overview

This flow handles the complete lifecycle of starting the FluidMCP backend server with dynamic MCP management capabilities, from CLI input validation through server readiness.

## Feature Flow

```
fmcp serve --secure --mongodb-uri mongodb://localhost:27017
server.py · run() → main(args)
       │
       ▼
┌────────────────────────────────────┐
│  1. Parse & Validate CLI Args     │
│  server.py · run()                 │
└────────────────────────────────────┘
       │
       ▼
< secure mode enabled? >
  server.py:757
       │
   [no] ────────────────────────────────────────────► Continue (no token required)
       │
   [yes]
       ▼
< token provided? >
  (CLI --token or env FMCP_BEARER_TOKEN)
  server.py:784-788
       │
   [yes] ────────────────────────────────────────────► Use provided token
       │
   [no]
       ▼
┌────────────────────────────────────┐
│  Generate Bearer Token             │
│  server.py:790-808                 │
│  secrets.token_urlsafe(32)         │
└────────────────────────────────────┘
  ● Creates 32-byte secure token
  ● Saves to ~/.fmcp/tokens/current_token.txt (0o600)
  ● Prints to console (NOT in logs)
       │
       ▼
┌────────────────────────────────────┐
│  2. Choose Persistence Backend     │
│  server.py:598-618                 │
└────────────────────────────────────┘
       │
       ▼
< --in-memory flag? >
  server.py:601
       │
   [yes] ────────────────────────────────────────────► InMemoryBackend (ephemeral)
       │                                                server.py:602-604
       │
   [no]
       ▼
┌────────────────────────────────────┐
│  3. Connect to MongoDB             │
│  server.py:606-618                 │
│  connect_with_retry()              │
└────────────────────────────────────┘
  ● MongoDB URI from CLI/env/default
  ● Retry: 3 attempts with exponential backoff (2s, 4s, 8s)
  ● Timeouts: server=30s, connect=10s, socket=45s
       │
       ▼
< MongoDB connection success? >
  server.py:404-447
       │
   [no] ──► < --require-persistence flag? >
       │        server.py:613
       │            │
       │        [yes] ──────────────────────────────► RuntimeError: "MongoDB required"
       │            │                                  Exit with error
       │        [no]
       │            ▼
       │    Log warning + continue with in-memory
       │    server.py:442-445
       │            │
       └────────────┘
       │
   [yes]
       ▼
┌────────────────────────────────────┐
│  4. Initialize Sentry (Optional)   │
│  server.py:620-621                 │
│  init_sentry()                     │
└────────────────────────────────────┘
  ● Only if SENTRY_DSN env var set
  ● Filters out /health and /metrics
       │
       ▼
┌────────────────────────────────────┐
│  5. Create ServerManager           │
│  server.py:623-629                 │
│  ServerManager(persistence)        │
└────────────────────────────────────┘
  ● Manages MCP server processes
  ● Starts idle cleanup background task
  ● Idle timeout: 3600s (1 hour, configurable)
       │
       ▼
┌────────────────────────────────────┐
│  6. Create FastAPI App             │
│  server.py:631-639                 │
│  create_app()                      │
└────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────┐
│  Build Middleware Stack            │
│  server.py:142-234                 │
└────────────────────────────────────┘
       │
       ├──► CORS Setup
       │    server.py:143-164
       │    │
       │    ▼
       │    < allowed_origins provided? >
       │        │
       │    [no] ──► Default: localhost only
       │        │    ["http://localhost:*", "http://127.0.0.1:*"]
       │        │
       │    [yes]
       │        ▼
       │    < wildcard "*" in origins? >
       │        │
       │    [yes] ──► Log security warning
       │        │     server.py:152-154
       │        │
       │    [no]
       │        └──► Use provided origins
       │
       ├──► Request Size Limiter
       │    server.py:166-234
       │    │
       │    ▼
       │    Max size: 10MB default (MAX_REQUEST_SIZE_MB env)
       │    NOTE: Only checks Content-Length header
       │    ⚠️  Chunked transfer encoding can bypass
       │    ⚠️  Requires server-level limits (Nginx, etc.)
       │
       └──► Store Managers in app.state
            server.py:236-238
       │
       ▼
┌────────────────────────────────────┐
│  Check MongoDB Availability        │
│  server.py:240-248                 │
└────────────────────────────────────┘
       │
       ▼
< MongoDB configured? >
  (db_manager.client exists)
  server.py:241
       │
   [no] ──────────────────────────────────────────────► Log ephemeral mode warning
       │                                                 server.py:242-248
       │                                                 ⚠️  All data lost on restart
       │                                                 ⚠️  No persistence
       │
   [yes] ────────────────────────────────────────────► Continue
       │
       ▼
┌────────────────────────────────────┐
│  Set Secure Mode (if enabled)      │
│  server.py:250-254                 │
└────────────────────────────────────┘
  ● Sets FMCP_BEARER_TOKEN env var
  ● Sets FMCP_SECURE_MODE="true"
       │
       ▼
┌────────────────────────────────────┐
│  7. Include API Routers            │
│  server.py:256-263                 │
└────────────────────────────────────┘
       │
       ├──► Management API
       │    server.py:257
       │    router from api/management.py
       │    Prefix: /api
       │    Endpoints: /api/servers, /api/servers/{id}/start, etc.
       │
       ├──► Dynamic MCP Router
       │    server.py:261-262
       │    create_dynamic_router(server_manager)
       │    No prefix (routes: /{server}/mcp, /{server}/sse, etc.)
       │
       └──► Core Endpoints
            server.py:273-399
            • GET /health → health_check()
            • GET /metrics → metrics()
            • GET / → root()
       │
       ▼
┌────────────────────────────────────┐
│  8. Serve Frontend                 │
│  server.py:266                     │
│  setup_frontend_routes()           │
└────────────────────────────────────┘
  ● Mounts React static files at /
  ● Frontend available at root path
       │
       ▼
┌────────────────────────────────────┐
│  9. Load Models from Persistence   │
│  server.py:641-646                 │
│  load_models_from_persistence()    │
└────────────────────────────────────┘
       │
       ▼
< MongoDB connected? >
  server.py:641
       │
   [no] ──────────────────────────────────────────────► Skip model loading
       │                                                 server.py:646
       │
   [yes]
       ▼
┌────────────────────────────────────┐
│  Query LLM Models                  │
│  server.py:449-576                 │
│  db_manager.list_llm_models()      │
└────────────────────────────────────┘
       │
       ▼
< models found? >
  server.py:471-475
       │
   [no] ──────────────────────────────────────────────► Log "No models found"
       │                                                 server.py:472
       │                                                 Return 0
       │
   [yes]
       ▼
For each model:
  │
  ▼
  < model type == "replicate"? >
       │
   [yes]
       ▼
       ┌────────────────────────────────────┐
       │  Initialize Replicate Client       │
       │  server.py:496-534                 │
       │  ReplicateClient(model_id, config) │
       └────────────────────────────────────┘
       ● Perform health check
       ● Register in global registry
       ● Handle race conditions (TOCTOU protection)
       │
       ▼
       < health check success? >
           │
       [no] ──► Close client, log warning
           │    server.py:532-534
           │
       [yes]
           ▼
           Register in _replicate_clients
           Register in _llm_models_config
           server.py:519-521
       │
       │
   [no]
       ▼
       < model type in ("vllm", "ollama", "lmstudio")? >
           │
       [yes]
           ▼
           ┌────────────────────────────────────┐
           │  Launch LLM Process                │
           │  server.py:538-562                 │
           │  launch_single_llm_model()         │
           └────────────────────────────────────┘
           ● Spawns subprocess
           ● Registers in process registry
           │
           ▼
           < launch success? >
               │
           [no] ──► Log warning
               │    server.py:562
               │
           [yes]
               ▼
               Register in process registry
               Register in _llm_models_config
               server.py:552-559
       │
       │
   [no]
       ▼
       Log "Unsupported model type"
       server.py:565
       │
       └──────────────────────────────────────────────► Continue to next model
       │
       ▼
Log total loaded count
server.py:571, 644
       │
       ▼
┌────────────────────────────────────┐
│  10. Setup Signal Handlers         │
│  server.py:648-663                 │
└────────────────────────────────────┘
  ● SIGINT (Ctrl+C)
  ● SIGTERM (termination request)
  ● SIGHUP (hangup, Unix only)
       │
       ▼
┌────────────────────────────────────┐
│  11. Configure Uvicorn             │
│  server.py:665-684                 │
│  Config(app, host, port, ...)      │
└────────────────────────────────────┘
  ● Host: from CLI --host (default: 0.0.0.0)
  ● Port: from CLI --port or $PORT (default: 8099)
  ● Loop: asyncio
  ● Log level: info
       │
       ▼
┌────────────────────────────────────┐
│  12. Start Uvicorn Server          │
│  server.py:686-694                 │
│  server.serve()                    │
└────────────────────────────────────┘
  ● Log startup messages
  ● Swagger UI URL: /docs
  ● Health check URL: /health
       │
       ▼
  ✓ Server ready: http://0.0.0.0:8099

  No MCP servers loaded (added dynamically via API)
```

## Key Decision Points

| Decision | Location | Yes path | No path |
|----------|----------|----------|------------|
| Secure mode enabled? | server.py:757 | Check for token | Continue without auth |
| Token provided? | server.py:784-788 | Use provided token | Generate new token |
| In-memory mode? | server.py:601 | InMemoryBackend | Try MongoDB |
| MongoDB connection success? | server.py:404-447 | Continue | Check --require-persistence |
| --require-persistence flag? | server.py:613 | Exit with error | Warn + continue with in-memory |
| MongoDB configured? | server.py:241 | Continue | Log ephemeral warning |
| Wildcard CORS? | server.py:152 | Log security warning | Use origins |
| MongoDB connected (model load)? | server.py:641 | Load models | Skip |
| Models found? | server.py:471 | Load each model | Log "none found" |
| Model type replicate? | server.py:496 | Initialize Replicate client | Check other types |
| Replicate health check success? | server.py:512 | Register client | Close + log warning |
| Model type vllm/ollama/lmstudio? | server.py:536 | Launch subprocess | Unsupported type |
| Process launch success? | server.py:551 | Register | Log warning |

## Side Effects

| Step | Side Effect | Where |
|------|-------------|-------|
| 1 | Generates bearer token (if secure + no token) | server.py:790-808 |
| 1 | Saves token to ~/.fmcp/tokens/current_token.txt (0o600) | server.py:795 |
| 1 | Prints token to console | server.py:797-805 |
| 1 | Sets FMCP_BEARER_TOKEN env var | server.py:252 |
| 3 | Creates AsyncIOMotorClient with connection pool | database.py:230-243 |
| 3 | Pings MongoDB to verify connection | database.py:251 |
| 3 | Creates indexes on collections | database.py:322-376 |
| 3 | Creates capped log collection (100MB) | database.py:361-373 |
| 4 | Initializes Sentry SDK (if configured) | server.py:33-68 |
| 5 | Starts idle cleanup background task | server_manager.py:1126-1136 |
| 6 | Adds CORS middleware | server.py:158-164 |
| 6 | Adds request size limiter | server.py:184-227 |
| 6 | Stores managers in app.state | server.py:236-238 |
| 7 | Includes Management API router | server.py:257 |
| 7 | Creates Dynamic MCP router | server.py:261-262 |
| 8 | Mounts frontend static files | frontend_utils.py:setup_frontend_routes() |
| 9 | Initializes Replicate clients (with health checks) | server.py:496-534 |
| 9 | Spawns vLLM/Ollama/LM Studio processes | server.py:538-562 |
| 10 | Registers signal handlers (SIGINT, SIGTERM, SIGHUP) | server.py:648-663 |
| 12 | Binds HTTP server to port | server.py:684, uvicorn.run() |

## Error Paths

| Trigger | Response | Code |
|---------|----------|------|
| MongoDB unavailable + --require-persistence | RuntimeError, exit | server.py:438-440 |
| MongoDB unavailable + no flag | Warning, continue with in-memory | server.py:442-445 |
| Invalid MAX_REQUEST_SIZE_MB env | Log warning, use default 10MB | server.py:176-181 |
| Invalid pool size env vars | Log warning, use defaults | database.py:187-227 |
| Sentry init fails | Log error, continue without Sentry | server.py:68 |
| Model health check fails | Close client, log warning, skip | server.py:532-534 |
| Model launch fails | Log warning, continue | server.py:562 |
| Port already in use | uvicorn startup fails | uvicorn (external) |
| Invalid token in request | 401 Unauthorized | auth.py:verify_token() |
| Request body > 10MB | 413 Payload Too Large | server.py:222-226 |

## Step Reference

| Step | Name | File | Function | Notes |
|------|------|------|----------|-------|
| 1 | Parse CLI Args | server.py | run() | Validate flags, generate/load token |
| 2 | Choose Backend | server.py | main() | MongoDB or in-memory |
| 3 | Connect MongoDB | repositories/database.py | DatabaseManager.connect() | Retry with backoff |
| 4 | Init Sentry | server.py | init_sentry() | Optional error tracking |
| 5 | Create ServerManager | services/server_manager.py | ServerManager() | Process lifecycle management |
| 6 | Create FastAPI App | server.py | create_app() | Build middleware stack |
| 7 | Include Routers | server.py | create_app() | Management + Dynamic + Core |
| 8 | Serve Frontend | services/frontend_utils.py | setup_frontend_routes() | React static files |
| 9 | Load Models | server.py | load_models_from_persistence() | LLM models from DB |
| 10 | Signal Handlers | server.py | main() | Graceful shutdown |
| 11 | Configure Uvicorn | server.py | main() | Server settings |
| 12 | Start Server | server.py | main() → uvicorn.run() | Bind to port |

## Graceful Shutdown Flow

When SIGINT/SIGTERM received:

```
Signal received
  ↓
shutdown_event.set()
  ↓
Stop idle cleanup task
  server_manager.stop_idle_cleanup_task()
  ↓
Stop all MCP servers (10s timeout)
  server_manager.shutdown_all()
  ↓
Close database connection
  persistence.disconnect()
  ↓
Exit
```

## MongoDB Retry Logic

```
Attempt 1
  ↓
< success? > ──[yes]──► Connected
  │
[no]
  ↓
Wait 2s (2^1)
  ↓
Attempt 2
  ↓
< success? > ──[yes]──► Connected
  │
[no]
  ↓
Wait 4s (2^2)
  ↓
Attempt 3
  ↓
< success? > ──[yes]──► Connected
  │
[no]
  ↓
< --require-persistence? >
  │
[yes] ──► RuntimeError: Exit
  │
[no] ──► Warning: Continue with in-memory
```

## Security Checklist

- ✓ Bearer token generated securely (`secrets.token_urlsafe(32)`)
- ✓ Token file permissions: 0o600 (owner read/write only)
- ✓ Token never logged (only printed to console on generation)
- ✓ CORS default: localhost only (explicit allowlist required)
- ✓ Request size limited (10MB default)
- ✓ MongoDB TLS validation enabled by default
- ✓ Sensitive data redacted in error messages
- ✓ Environment variables validated (no placeholders)
- ✓ Rate limiting available (Redis or in-memory)
- ✓ Sentry filters /health and /metrics from tracking
