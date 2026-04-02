# FMCP Serve → Architecture Diagram

> Shows component relationships and module structure for the `fmcp serve` command, which creates a standalone API server for dynamic MCP server management.

## Overview

The `fmcp serve` command creates a persistent HTTP API server that manages MCP servers dynamically. Unlike `fmcp run`, this mode starts with **no MCP servers loaded** — all servers are added, started, and stopped via REST API calls. The architecture is layered with FastAPI at the core, MongoDB for persistence (with in-memory fallback), and React frontend for UI.

## Architecture Layers

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│  ENTRY / CLI LAYER                                                                  │
│                                                                                     │
│  ┌───────────────────────────────────────────────────────────────────────────┐    │
│  │  Serve Command Handler                                                     │    │
│  │  cli.py                                                                    │    │
│  │  main() → serve parser                                                     │    │
│  │  • Parse CLI args (--secure, --mongodb-uri, --token, --port)              │    │
│  │  • Generate/load bearer token (if secure mode)                            │    │
│  │  • Bootstrap server components                                             │    │
│  └───────────────────────────────────────────────────────────────────────────┘    │
│                                    ↓                                                │
└────────────────────────────────────────────────────────────────────────────────────┘
                                     ↓
┌────────────────────────────────────────────────────────────────────────────────────┐
│  PERSISTENCE LAYER                                                                  │
│                                                                                     │
│  ┌─────────────────────────────────┐     ┌─────────────────────────────────┐      │
│  │  MongoDB Backend                │  OR │  In-Memory Backend              │      │
│  │  database.py                    │     │  memory.py                      │      │
│  │  DatabaseManager                │     │  InMemoryBackend                │      │
│  │  • Connect to MongoDB           │     │  • Ephemeral storage            │      │
│  │  • Retry with backoff           │     │  • No persistence               │      │
│  │  • Server configs               │     │  • Development mode             │      │
│  │  • Instance state               │     │                                 │      │
│  │  • Logs (capped collection)    │     │                                 │      │
│  │  • LLM models                   │     │                                 │      │
│  └─────────────────────────────────┘     └─────────────────────────────────┘      │
│                                    ↓                                                │
└────────────────────────────────────────────────────────────────────────────────────┘
                                     ↓
┌────────────────────────────────────────────────────────────────────────────────────┐
│  SERVER ORCHESTRATION LAYER                                                         │
│                                                                                     │
│  ┌───────────────────────────────────────────────────────────────────────────┐    │
│  │  ServerManager                                                             │    │
│  │  server_manager.py                                                         │    │
│  │  • MCP server lifecycle (start/stop/restart)                              │    │
│  │  • Process registry (in-memory)                                           │    │
│  │  • Health checking                                                         │    │
│  │  • Idle cleanup (background task)                                         │    │
│  │  • Auto-restart on crash                                                  │    │
│  │  • Operation locks (prevent concurrent ops)                               │    │
│  └───────────────────────────────────────────────────────────────────────────┘    │
│                                    ↓                                                │
└────────────────────────────────────────────────────────────────────────────────────┘
                                     ↓
┌────────────────────────────────────────────────────────────────────────────────────┐
│  APPLICATION LAYER                                                                  │
│                                                                                     │
│  ┌───────────────────────────────────────────────────────────────────────────┐    │
│  │  FastAPI Application                                                       │    │
│  │  server.py                                                                 │    │
│  │  create_app(db_manager, server_manager, secure_mode, ...)                 │    │
│  │                                                                            │    │
│  │  ┌─── Middleware Stack ─────────────────────────────────────────────┐    │    │
│  │  │  1. CORS (allow_origins from CLI/env)                            │    │    │
│  │  │  2. Request size limiter (10MB default, configurable)            │    │    │
│  │  │  3. Bearer token auth (if secure mode enabled)                   │    │    │
│  │  └──────────────────────────────────────────────────────────────────┘    │    │
│  │                                                                            │    │
│  │  ┌─── Core Endpoints ───────────────────────────────────────────────┐    │    │
│  │  │  GET  /               → API info (name, version, docs)            │    │    │
│  │  │  GET  /health         → Health check (DB status, model count)    │    │    │
│  │  │  GET  /metrics        → Prometheus metrics                        │    │    │
│  │  │  GET  /docs           → Swagger UI                                │    │    │
│  │  └──────────────────────────────────────────────────────────────────┘    │    │
│  └───────────────────────────────────────────────────────────────────────────┘    │
│                                    ↓                                                │
└────────────────────────────────────────────────────────────────────────────────────┘
           ↓                         ↓                         ↓
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│  API ROUTERS         │  │  DYNAMIC MCP ROUTER  │  │  FRONTEND            │
│                      │  │                      │  │                      │
│  ┌────────────────┐  │  │  ┌────────────────┐ │  │  ┌────────────────┐ │
│  │ Management API │  │  │  │ Dynamic Router │ │  │  │ React App      │ │
│  │ management.py  │──┼──┼─►│ package_       │ │  │  │ Static Files   │ │
│  │                │  │  │  │ launcher.py    │ │  │  │ Served at /    │ │
│  │ ─────────────  │  │  │  │ create_dynamic │ │  │  └────────────────┘ │
│  │ POST /api/     │  │  │  │ _router()      │ │  │                      │
│  │ servers        │  │  │  │                │ │  │  ┌────────────────┐ │
│  │ • Create       │  │  │  │ ─────────────  │ │  │  │ Frontend Utils │ │
│  │ • List         │  │  │  │ POST /{server}/│ │  │  │ frontend_      │ │
│  │ • Get          │  │  │  │ mcp            │ │  │  │ utils.py       │ │
│  │ • Update       │  │  │  │ • JSON-RPC     │ │  │  │ setup_frontend │ │
│  │ • Delete       │  │  │  │   proxy        │ │  │  │ _routes()      │ │
│  │                │  │  │  │                │ │  │  └────────────────┘ │
│  │ POST /api/     │  │  │  │ POST /{server}/│ │  │                      │
│  │ servers/{id}/  │  │  │  │ sse            │ │  │                      │
│  │ • start        │  │  │  │ • Server-Sent  │ │  │                      │
│  │ • stop         │  │  │  │   Events       │ │  │                      │
│  │ • restart      │  │  │  │                │ │  │                      │
│  │                │  │  │  │ GET /{server}/ │ │  │                      │
│  │ GET /api/      │  │  │  │ mcp/tools/list │ │  │                      │
│  │ servers/{id}/  │  │  │  │ • Tool         │ │  │                      │
│  │ • status       │  │  │  │   discovery    │ │  │                      │
│  │ • logs         │  │  │  │                │ │  │                      │
│  │ • env          │  │  │  │ POST /{server}/│ │  │                      │
│  │                │  │  │  │ mcp/tools/call │ │  │                      │
│  │ ─────────────  │  │  │  │ • Tool exec    │ │  │                      │
│  │ Auth:          │  │  │  └────────────────┘ │  │                      │
│  │ • verify_token │  │  │  Routes created    │  │                      │
│  │   (Bearer)     │  │  │  dynamically when  │  │                      │
│  │                │  │  │  servers start     │  │                      │
│  │ Rate Limiting: │  │  └──────────────────────┘  └──────────────────────┘
│  │ • check_rate_  │  │
│  │   limit()      │  │
│  │ • Redis/       │  │
│  │   In-memory    │  │
│  └────────────────┘  │
└──────────────────────┘
```

## Component Summary

| Component | File | Class/Function | Role |
|-----------|------|---------------|------|
| **Entry Point** |
| Serve Handler | cli.py | main() → serve parser | Parse CLI args, bootstrap server |
| Token Generator | server.py | save_token_to_file() | Generate/save bearer token securely |
| **Persistence** |
| MongoDB Backend | repositories/database.py | DatabaseManager | Primary persistence (production) |
| In-Memory Backend | repositories/memory.py | InMemoryBackend | Fallback storage (development) |
| Base Interface | repositories/base.py | PersistenceBackend | Abstract persistence interface |
| **Orchestration** |
| Server Manager | services/server_manager.py | ServerManager | MCP server lifecycle orchestration |
| Health Checker | services/health_checker.py | HealthChecker | Process health validation |
| Package Launcher | services/package_launcher.py | launch_mcp_using_fastapi_proxy() | Spawn MCP subprocess with pipes |
| Process Initializer | services/package_launcher.py | initialize_mcp_server() | JSON-RPC handshake |
| **Application** |
| FastAPI App | server.py | create_app() | Create app with CORS, auth, routes |
| Lifespan Manager | server.py | lifespan() | Startup/shutdown lifecycle |
| Connection Retry | server.py | connect_with_retry() | MongoDB retry with backoff |
| Model Loader | server.py | load_models_from_persistence() | Load LLM models on startup |
| **API Layer** |
| Management API | api/management.py | router | REST endpoints for server CRUD |
| Dynamic Router | services/package_launcher.py | create_dynamic_router() | MCP request routing |
| Auth Middleware | auth.py | verify_token() | Bearer token validation |
| Rate Limiter | utils/rate_limiter.py | check_rate_limit() | Request rate limiting |
| **Frontend** |
| Frontend Setup | services/frontend_utils.py | setup_frontend_routes() | Serve React app |
| Static Files | – | – | Built React app served at / |
| **Metrics** |
| Metrics Registry | services/metrics.py | get_registry() | Prometheus metrics collection |
| Metrics Collector | services/metrics.py | MetricsCollector | Per-server metrics tracking |

## Key Data Flow

```
CLI Args
  ↓
Parse & Validate
  ↓
MongoDB/In-Memory Connection
  ↓
ServerManager(db_manager)
  ↓
create_app(db_manager, server_manager, ...)
  ↓
  ├─→ CORS Middleware
  ├─→ Request Size Limiter
  ├─→ Bearer Token Auth
  ├─→ Management API (/api/*)
  ├─→ Dynamic MCP Router (/{server}/*)
  ├─→ Frontend Routes (/)
  ├─→ Health (/health)
  └─→ Metrics (/metrics)
  ↓
uvicorn.run(app, host="0.0.0.0", port=8099)
  ↓
HTTP Server Listening
```

## Component Interactions

### Server Creation Flow
```
User → POST /api/servers
  → Management API (management.py)
  → DatabaseManager.save_server_config()
  → MongoDB (fluidmcp_servers collection)
```

### Server Start Flow
```
User → POST /api/servers/{id}/start
  → Management API (management.py)
  → ServerManager.start_server()
  → launch_mcp_using_fastapi_proxy()
  → subprocess.Popen([command, args])
  → initialize_mcp_server() (JSON-RPC handshake)
  → DatabaseManager.save_instance_state()
  → Return server status
```

### MCP Request Flow
```
User → POST /{server}/mcp
  → Dynamic Router (create_dynamic_router)
  → ServerManager.processes[server_id]
  → process.stdin.write(json_rpc_request)
  → process.stdout.readline() (response)
  → Return JSON-RPC response
```

### Health Check Flow
```
Load Balancer → GET /health
  → Health endpoint (server.py)
  → DatabaseManager.client.admin.command('ping')
  → Count registered models
  → Return {status, database, models, version}
```

## Deployment Architecture

### Production (Railway)
```
┌─────────────────────────────────────────────────────┐
│  Railway Container                                   │
│                                                      │
│  ┌────────────────────────────────────────────┐    │
│  │  FluidMCP Backend                           │    │
│  │  fmcp serve --secure                        │    │
│  │  Port: $PORT (assigned by Railway)         │    │
│  │  Token: $FMCP_BEARER_TOKEN (env var)       │    │
│  └────────────────────────────────────────────┘    │
│                     ↕                                │
│  ┌────────────────────────────────────────────┐    │
│  │  MongoDB Service                            │    │
│  │  $MONGODB_URI (Railway-provided)           │    │
│  └────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
                      ↕
              Internet (HTTPS)
```

### Development (Local)
```
┌─────────────────────────────────────────────────────┐
│  Local Machine                                       │
│                                                      │
│  ┌────────────────────────────────────────────┐    │
│  │  FluidMCP Backend                           │    │
│  │  fmcp serve --in-memory                     │    │
│  │  Port: 8099                                 │    │
│  │  Token: auto-generated                      │    │
│  └────────────────────────────────────────────┘    │
│                                                      │
│  (No MongoDB required)                               │
└─────────────────────────────────────────────────────┘
                      ↕
              Localhost (HTTP)
```

## Security Features

| Layer | Feature | Implementation |
|-------|---------|---------------|
| **Authentication** | Bearer Token | HTTPBearer() + verify_token() |
| **Token Storage** | Secure File | ~/.fmcp/tokens/ (0o600 permissions) |
| **Token Source** | Priority Order | CLI arg > Env var > Auto-generate |
| **CORS** | Allowlist | Default: localhost only |
| **Request Size** | Body Limit | 10MB default (MAX_REQUEST_SIZE_MB) |
| **Rate Limiting** | Redis/In-Memory | check_rate_limit() per endpoint |
| **Input Validation** | Sanitization | _sanitize_mongodb_input() |
| **Error Redaction** | Sensitive Data | sanitize_error_message() |
| **TLS Validation** | Certificate Check | Secure by default (MongoDB) |
| **Env Vars** | Placeholder Filter | is_placeholder() check |

## Background Tasks

| Task | Manager | Function | Purpose |
|------|---------|----------|---------|
| Idle Cleanup | ServerManager | _idle_cleanup_loop() | Stop idle servers (1hr default) |
| Health Monitoring | HealthChecker | (periodic checks) | Validate process health |
| Log Retry | DatabaseManager | _retry_failed_logs() | Retry buffered log writes |
| Metrics Update | MetricsCollector | (on request) | Update server metrics |

## Storage Schema (MongoDB)

| Collection | Purpose | Key Fields |
|-----------|---------|------------|
| fluidmcp_servers | Server configs | id, name, mcp_config, enabled, restart_policy |
| fluidmcp_server_instances | Runtime state | server_id, state, pid, start_time, last_used_at |
| fluidmcp_server_logs | Process logs | server_name, timestamp, stream, content (capped) |
| fluidmcp_llm_models | LLM models | model_id, type, model, api_key, endpoints |
| fluidmcp_llm_model_versions | Version history | model_id, version, archived_at (for rollback) |

## Notes

- **No Pre-loaded Servers**: Unlike `fmcp run`, serve mode starts with NO MCP servers
- **Dynamic Management**: All servers added/started/stopped via REST API
- **MongoDB Optional**: Falls back to in-memory if MongoDB unavailable (unless --require-persistence)
- **Bearer Token Critical**: Must set FMCP_BEARER_TOKEN env var on Railway to prevent token regeneration on restart
- **Ephemeral Containers**: Railway containers restart frequently, persistence prevents state loss
- **Health Endpoint**: Railway uses /health for monitoring (checks DB connection + model count)
- **Port Configuration**: Railway assigns port via $PORT env var
- **CORS Security**: Default localhost-only, wildcard (*) shows security warning
- **Auto-reclone**: Missing GitHub repo directories auto-reclone on server start (Railway fix)
- **Optimistic Locking**: PID-based locking prevents stale state race conditions
- **Capped Logs**: Server logs limited to 100MB (oldest auto-removed)
