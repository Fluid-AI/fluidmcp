# GET /health — Data Flow Diagram

> Public health check endpoint that verifies MongoDB connectivity, counts registered models, and returns a structured status JSON used by load balancers and Docker HEALTHCHECK.

## Overview

`GET /health` is an unauthenticated FastAPI endpoint defined in `server.py`. On every call it performs a live MongoDB `ping`, reads two in-memory registries for model counts, derives an overall status string, and returns a single JSON document. It is intentionally excluded from request-counter instrumentation to avoid metric pollution from frequent health-check probes.

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  INPUT                                                                       │
│                                                                              │
│   HTTP client (load balancer / Docker / curl)                                │
│                                                                              │
│   GET /health                                                                │
│   No Authorization header required                                           │
│   No request body                                                            │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                │  HTTP GET (no auth, no body)
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  HANDLER                                                                     │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  health_check()                                                       │   │
│  │  fluidmcp/cli/server.py · FastAPI @app.get("/health")                │   │
│  └──────────────┬────────────────────┬──────────────────────────────────┘   │
└─────────────────┼────────────────────┼────────────────────────────────────--┘
                  │                    │
     ┌────────────┘                    └────────────────────┐
     │  branch A                                            │  branch B
     ▼                                                      ▼
┌────────────────────────────────────────┐   ┌─────────────────────────────────────────┐
│  PROCESSING — branch A                 │   │  PROCESSING — branch B                  │
│  MongoDB Liveness Ping                 │   │  In-Memory Registry Reads               │
│                                        │   │                                         │
│  Precondition check:                   │   │  ┌───────────────────────────────────┐  │
│  hasattr(db_manager, 'client')         │   │  │  len(_replicate_clients)          │  │
│    AND db_manager.client is not None   │   │  │  fluidmcp/cli/services/           │  │
│                                        │   │  │  replicate_client.py              │  │
│  ┌─────────────────────────────────┐   │   │  │  · module-level dict              │  │
│  │  db_manager.client              │   │   │  └──────────────┬────────────────────┘  │
│  │  .admin.command('ping')         │   │   │                 │ ──[int]──►             │
│  │  (async, motor driver)          │   │   │                 │  replicate_count       │
│  │  fluidmcp/cli/repositories/     │   │   │                 │                        │
│  │  database.py · DatabaseManager  │   │   │  ┌───────────────────────────────────┐  │
│  └──────────┬──────────────────────┘   │   │  │  len(_llm_models_config)          │  │
│             │                          │   │  │  fluidmcp/cli/services/           │  │
│     success │  exception               │   │  │  llm_provider_registry.py         │  │
│     ────────┼─────────────────────     │   │  │  · module-level dict              │  │
│             │             │            │   │  └──────────────┬────────────────────┘  │
│             ▼             ▼            │   │                 │ ──[int]──►             │
│         "connected"    "error"         │   │                 │  total_models          │
│          db_status     db_status       │   └─────────────────┼───────────────────────┘
│          db_error=None db_error=str(e) │                     │
└───────────────────────────────────────┘                     │
                  │  ──[str, str|None]──►                      │  ──[int, int]──►
                  │  (db_status, db_error)                     │  (replicate_count,
                  └──────────────────┬─────────────────────────┘   total_models)
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STATUS DETERMINATION                                                        │
│                                                                              │
│  fluidmcp/cli/server.py · health_check() — lines 311-319                    │
│                                                                              │
│         < db_status == "error" ? >                                           │
│                YES │         NO │                                            │
│                    │            └──────► < db_status == "disconnected" ? >  │
│                    │                           YES │           NO │          │
│                    │                               │              │          │
│                    │              < total_models == 0 ? >         │          │
│                    │                 YES │        NO │            │          │
│                    │                    │           │             │          │
│                    ▼                    ▼           ▼             ▼          │
│               "degraded"          "starting"  "degraded"     "healthy"      │
│         (DB error, service up)   (fresh boot,  (DB lost,    (DB connected,  │
│                                  no models)   models live)  persistence on) │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     │  ──[str]──► overall_status
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  RESPONSE ASSEMBLY                                                           │
│                                                                              │
│  fluidmcp/cli/server.py · health_check() — lines 321-337                    │
│                                                                              │
│  {                                                                           │
│    "status":    overall_status,           // "healthy"|"degraded"|"starting"│
│    "timestamp": datetime.utcnow() + "Z",  // ISO-8601 UTC                   │
│    "database": {                                                             │
│       "status":              db_status,   // "connected"|"error"|"disconn." │
│       "type":                db_type,     // e.g. "DatabaseManager"         │
│       "error":               db_error,    // null or exception message      │
│       "persistence_enabled": bool         // True only when "connected"     │
│    },                                                                        │
│    "models": {                                                               │
│       "total":   total_models,            // len(_llm_models_config)        │
│       "by_type": { "replicate": int }     // len(_replicate_clients)        │
│    },                                                                        │
│    "version":   app.version               // "2.0.0"                        │
│  }                                                                           │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │
                                │  HTTP 200 JSON
                                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  OUTPUT                                                                      │
│                                                                              │
│   Caller / Docker HEALTHCHECK / Railway load balancer                        │
│                                                                              │
│   HTTP 200 OK (always — unhealthy state is reported in body, not status)    │
│   Content-Type: application/json                                             │
│                                                                              │
│   Docker HEALTHCHECK (Dockerfile lines 66-67):                               │
│     curl -f http://localhost:${PORT}/health || exit 1                        │
│     --interval=30s  --timeout=10s  --start-period=40s  --retries=3          │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Phase Breakdown

### Input

| Property | Value |
|---|---|
| Method | `GET` |
| Path | `/health` |
| Auth required | No — intentionally public |
| Request body | None |
| Query params | None |

The endpoint is registered inside `create_server()` in `server.py` and is deliberately **not** wrapped in the `RequestTimer` dependency to avoid polluting `fluidmcp_requests_total` metrics with high-frequency load-balancer probes (see comment at line 274).

### Processing

Three independent data-gathering operations run sequentially in the handler (no concurrency primitives needed — each is either a single `await` or a `len()` call):

**1. MongoDB liveness ping (async I/O)**

- Guard: checks `hasattr(db_manager, 'client') and db_manager.client` before attempting the ping. If the guard fails, `db_status` stays `"disconnected"`.
- Live wire: `await db_manager.client.admin.command('ping')` — this is a real network round-trip to MongoDB, not a cached connection flag.
- Success path → `db_status = "connected"`, `db_error = None`
- Exception path → `db_status = "error"`, `db_error = str(e)` (exception message surfaced in response)
- The `ping` command is also used internally by `DatabaseManager.connect()` during startup, but the health endpoint calls it directly on the `client` object rather than through a dedicated `ping()` helper method.
- Source: `fluidmcp/cli/repositories/database.py · DatabaseManager`

**2. Replicate client count (in-memory)**

- `from .services.replicate_client import _replicate_clients`
- `replicate_count = len(_replicate_clients)` — module-level `Dict[str, ReplicateClient]`
- O(1), no I/O
- Source: `fluidmcp/cli/services/replicate_client.py`

**3. Total LLM model count (in-memory)**

- `from .services.llm_provider_registry import _llm_models_config`
- `total_models = len(_llm_models_config)` — module-level `Dict[str, dict]` populated by `initialize_llm_registry()`
- O(1), no I/O
- Source: `fluidmcp/cli/services/llm_provider_registry.py`

### Status Determination Logic

```
if db_status == "error":
    overall_status = "degraded"          # DB threw an exception
elif db_status == "disconnected":
    if total_models == 0:
        overall_status = "starting"      # No DB AND no models → still booting
    else:
        overall_status = "degraded"      # Models loaded but DB lost → persistence gone
else:  # db_status == "connected"
    overall_status = "healthy"
```

The three possible values map to operational states:

| `status` | Meaning |
|---|---|
| `healthy` | MongoDB is reachable; persistence is fully operational |
| `degraded` | Service is running and serving requests, but MongoDB is unreachable or erroring |
| `starting` | No database and no models — container is still initialising |

### Output

The handler always returns HTTP 200. Callers must inspect the `status` field in the body to distinguish healthy from degraded states. The Docker `HEALTHCHECK` uses `curl -f` which only fails on non-2xx responses, so a `"degraded"` body still keeps the container marked healthy at the infrastructure layer.

## Response Structure

```json
{
  "status": "healthy",
  "timestamp": "2026-04-08T12:34:56.789Z",
  "database": {
    "status": "connected",
    "type": "DatabaseManager",
    "error": null,
    "persistence_enabled": true
  },
  "models": {
    "total": 3,
    "by_type": {
      "replicate": 2
    }
  },
  "version": "2.0.0"
}
```

| Field | Type | Source | Description |
|---|---|---|---|
| `status` | `string` | Derived | Overall health: `"healthy"`, `"degraded"`, or `"starting"` |
| `timestamp` | `string` | `datetime.utcnow()` | ISO-8601 UTC timestamp of this response |
| `database.status` | `string` | MongoDB ping result | `"connected"`, `"error"`, or `"disconnected"` |
| `database.type` | `string` | `type(db_manager).__name__` | Class name of the backend (e.g. `"DatabaseManager"`, `"InMemoryBackend"`) |
| `database.error` | `string\|null` | Exception message | `null` on success; exception string on error |
| `database.persistence_enabled` | `bool` | `db_status == "connected"` | `true` only when MongoDB ping succeeded |
| `models.total` | `int` | `len(_llm_models_config)` | Total registered LLM models across all provider types |
| `models.by_type.replicate` | `int` | `len(_replicate_clients)` | Count of initialised Replicate provider clients |
| `version` | `string` | `app.version` | FluidMCP server version (default `"2.0.0"`) |

## Docker HEALTHCHECK

Defined in `Dockerfile` lines 63-67:

```dockerfile
# Health check for Railway monitoring
# Start period: 40s (allows MongoDB connection retry: 2s + 4s + 8s + startup time)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1
```

| Parameter | Value | Rationale |
|---|---|---|
| `--interval` | 30s | Checks every 30 seconds after the start period |
| `--timeout` | 10s | Kills the check if it takes longer than 10 seconds |
| `--start-period` | 40s | Grace period for MongoDB retry backoff (2 s + 4 s + 8 s + startup overhead) |
| `--retries` | 3 | Container marked unhealthy only after 3 consecutive failures |

## Data Flow Summary

| Step | Component | File | Function / Symbol | Data In | Data Out |
|---|---|---|---|---|---|
| 1 | FastAPI router | `fluidmcp/cli/server.py` | `@app.get("/health")` | HTTP GET request | Invokes `health_check()` |
| 2 | Health handler | `fluidmcp/cli/server.py` | `health_check()` | None (no params) | Orchestrates all sub-steps |
| 3 | MongoDB guard | `fluidmcp/cli/server.py` | `health_check()` lines 298-305 | `db_manager.client` reference | `True` / `False` (proceed or skip) |
| 4 | MongoDB ping | `fluidmcp/cli/repositories/database.py` | `db_manager.client.admin.command('ping')` | None | Raises or returns (success/failure) |
| 5 | DB status set | `fluidmcp/cli/server.py` | `health_check()` | Ping result or exception | `db_status: str`, `db_error: str\|None` |
| 6 | Replicate count | `fluidmcp/cli/services/replicate_client.py` | `_replicate_clients` | Module-level dict | `replicate_count: int` |
| 7 | LLM model count | `fluidmcp/cli/services/llm_provider_registry.py` | `_llm_models_config` | Module-level dict | `total_models: int` |
| 8 | Status logic | `fluidmcp/cli/server.py` | `health_check()` lines 311-319 | `db_status`, `total_models` | `overall_status: str` |
| 9 | Response build | `fluidmcp/cli/server.py` | `health_check()` lines 321-337 | All collected values | JSON dict |
| 10 | HTTP response | FastAPI / Starlette | — | JSON dict | HTTP 200 `application/json` |
