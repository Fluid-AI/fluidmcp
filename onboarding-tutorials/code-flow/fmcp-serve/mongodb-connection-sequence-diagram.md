# MongoDB Connection — Sequence Diagram

> Traces the full lifecycle of a MongoDB connection attempt inside `fmcp serve`: from `main()` through the retry loop in `connect_with_retry()`, into `DatabaseManager.connect()` / `init_db()`, down to the Motor async client ping, collection creation, and both the success path and the failure/fallback path.

---

## Participants

| Actor | File | Key Function / Role |
|---|---|---|
| **main()** | `fluidmcp/cli/server.py` | Entry point; constructs `DatabaseManager`, calls `connect_with_retry()` |
| **connect_with_retry()** | `fluidmcp/cli/server.py` | Retry loop with exponential backoff; decides fallback vs. hard-exit |
| **DatabaseManager** | `fluidmcp/cli/repositories/database.py` | Owns `init_db()` → `connect()` → `_init_collections()`; Motor client lifecycle |
| **MongoDB** | External (Motor async client) | Receives `ping` command and index/collection creation commands |

---

## Sequence

```
     main()                connect_with_retry()          DatabaseManager               MongoDB
     server.py             server.py                     repositories/                 External
                                                         database.py                   Motor client

       │                          │                             │                          │
       │                          │                             │                          │
       │  1. connect_with_retry(  │                             │                          │
       │     db_manager,          │                             │                          │
       │     max_retries=3,       │                             │                          │
       │     require_persistence) │                             │                          │
       │─────────────────────────►│                             │                          │
       │                          │                             │                          │
       │                          │  ╔══════════════════════════════════════════════════╗  │
       │                          │  ║  RETRY LOOP  (attempt = 1 … max_retries)        ║  │
       │                          │  ╚══════════════════════════════════════════════════╝  │
       │                          │                             │                          │
       │                          │  2. await db_manager        │                          │
       │                          │        .init_db()           │                          │
       │                          │  [attempt 1 / 3]            │                          │
       │                          │────────────────────────────►│                          │
       │                          │                             │                          │
       │                          │                             │  3. AsyncIOMotorClient(  │
       │                          │                             │     uri, serverSelection │
       │                          │                             │     TimeoutMS,           │
       │                          │                             │     connectTimeoutMS,    │
       │                          │                             │     socketTimeoutMS,     │
       │                          │                             │     maxPoolSize,         │
       │                          │                             │     minPoolSize,         │
       │                          │                             │     retryWrites=True,    │
       │                          │                             │     w="majority")        │
       │                          │                             │- - - - - - - - - - - - ►│
       │                          │                             │  [Motor client created]  │
       │                          │                             │◄- - - - - - - - - - - - │
       │                          │                             │                          │
       │                          │                             │  4. await admin          │
       │                          │                             │       .command('ping')   │
       │                          │                             │- - - - - - - - - - - - ►│
       │                          │                             │                          │
       │                          │        ╔════════════════════╧══════════════════════════╧═══╗
       │                          │        ║  BRANCH: ping result                              ║
       │                          │        ╚════════════════════╤══════════════════════════╤═══╝
       │                          │                             │                          │
       │   ╔═══════════════════════════════════════════════════════════════════════════════╗
       │   ║  SUCCESS PATH                                      │                          ║
       │   ╚═══════════════════════════════════════════════════════════════════════════════╝
       │                          │                             │   ping OK                │
       │                          │                             │◄- - - - - - - - - - - - │
       │                          │                             │                          │
       │                          │                             │  5a. self.db =           │
       │                          │                             │      client[db_name]     │
       │                          │                             │      (assign db handle)  │
       │                          │                             │                          │
       │                          │                             │  5b. await client        │
       │                          │                             │       .server_info()     │
       │                          │                             │  (check change-stream    │
       │                          │                             │   / replica-set support) │
       │                          │                             │- - - - - - - - - - - - ►│
       │                          │                             │◄- - - - - - - - - - - - │
       │                          │                             │                          │
       │                          │                             │  5c. _migrate_collection │
       │                          │                             │      _names()            │
       │                          │                             │  (rename old→new         │
       │                          │                             │   fluidmcp_* prefix)     │
       │                          │                             │- - - - - - - - - - - - ►│
       │                          │                             │◄- - - - - - - - - - - - │
       │                          │                             │                          │
       │                          │                             │  5d. _init_collections() │
       │                          │                             │  ┌───────────────────────┴─────────────────────┐
       │                          │                             │  │ fluidmcp_servers                            │
       │                          │                             │  │   create_index("id", unique=True)           │
       │                          │                             │  │                                             │
       │                          │                             │  │ fluidmcp_server_instances                   │
       │                          │                             │  │   create_index("server_id")                 │
       │                          │                             │  │                                             │
       │                          │                             │  │ fluidmcp_server_logs                        │
       │                          │                             │  │   capped collection (100 MB)                │
       │                          │                             │  │   create_index([server_name, timestamp])    │
       │                          │                             │  │                                             │
       │                          │                             │  │ fluidmcp_llm_models                         │
       │                          │                             │  │   create_index("model_id", unique=True)     │
       │                          │                             │  │                                             │
       │                          │                             │  │ fluidmcp_llm_model_versions                 │
       │                          │                             │  │   create_index([model_id, archived_at])     │
       │                          │                             │  │                                             │
       │                          │                             │  │ fluidmcp_crash_events                       │
       │                          │                             │  │   create_index([server_id, timestamp])      │
       │                          │                             │  │   TTL index on "timestamp"                  │
       │                          │                             │  │   expireAfterSeconds = 30 days × 86400      │
       │                          │                             │  └───────────────────────┬─────────────────────┘
       │                          │                             │- - - (all create_index)- ►│
       │                          │                             │◄- - - - - - - - - - - - │
       │                          │                             │                          │
       │                          │  6.  returns True           │                          │
       │                          │◄────────────────────────────│                          │
       │                          │                             │                          │
       │  7.  returns True        │                             │                          │
       │◄─────────────────────────│                             │                          │
       │                          │                             │                          │
       │  [main() continues:      │                             │                          │
       │   create ServerManager,  │                             │                          │
       │   build FastAPI app,     │                             │                          │
       │   load LLM models …]     │                             │                          │
       │                          │                             │                          │
       │   ╔═══════════════════════════════════════════════════════════════════════════════╗
       │   ║  FAILURE PATH  (ping raises ConnectionFailure or any Exception)              ║
       │   ╚═══════════════════════════════════════════════════════════════════════════════╝
       │                          │                             │                          │
       │                          │                             │   ping FAILS             │
       │                          │                             │◄ × × × × × × × × × × × ×│
       │                          │                             │                          │
       │                          │  8a. returns False          │                          │
       │                          │◄────────────────────────────│                          │
       │                          │                             │                          │
       │                          │  ┌──────────────────────────────────────────────────┐  │
       │                          │  │  attempt < max_retries?                          │  │
       │                          │  │  YES → wait_time = 2 ** attempt                  │  │
       │                          │  │          attempt 1 → wait 2 s                    │  │
       │                          │  │          attempt 2 → wait 4 s                    │  │
       │                          │  │          attempt 3 → wait 8 s (last; no sleep)   │  │
       │                          │  │  then loop back to step 2 with attempt + 1       │  │
       │                          │  └──────────────────────────────────────────────────┘  │
       │                          │                             │                          │
       │                          │  ┌──────────────────────────────────────────────────┐  │
       │                          │  │  All retries exhausted                           │  │
       │                          │  │                                                   │  │
       │                          │  │  require_persistence = True?                     │  │
       │                          │  │    YES → raise RuntimeError(                     │  │
       │                          │  │              "MongoDB connection required…")     │  │
       │                          │  │            → caller catches → sys.exit(1)        │  │
       │                          │  │            (intentional Railway crash loop)      │  │
       │                          │  │                                                   │  │
       │                          │  │  require_persistence = False?                    │  │
       │                          │  │    YES → returns False                           │  │
       │                          │  └──────────────────────────────────────────────────┘  │
       │                          │                             │                          │
       │  8b. returns False       │                             │                          │
       │◄─────────────────────────│                             │                          │
       │                          │                             │                          │
       │  [main() continues with  │                             │                          │
       │   InMemoryBackend —      │                             │                          │
       │   state lost on restart] │                             │                          │
       │                          │                             │                          │
```

---

## Notes

- **Retry backoff formula**: `wait_time = 2 ** attempt` — attempt 1 waits 2 s, attempt 2 waits 4 s; after the third (final) attempt the sleep is skipped and the exhaustion branch is entered immediately.

- **`require_persistence` behaviour**:
  - `False` (default): after all retries are exhausted, `connect_with_retry()` returns `False` and `main()` silently falls back to `InMemoryBackend`. Server state is **not persisted** across restarts and a warning is logged.
  - `True` (`--require-persistence` CLI flag): after exhaustion a `RuntimeError` is raised, which propagates up and causes the container to exit with code 1. On Railway this triggers an intentional crash-loop until MongoDB becomes reachable.

- **`init_db()` is the single public entry point** from `connect_with_retry()`. Internally it calls `connect()` first; only if that succeeds does it proceed to `_migrate_collection_names()` and then create all indexes / collections.

- **Change-stream detection** happens inside `connect()` (after the ping succeeds): `server_info()` checks the MongoDB major version, then `replSetGetStatus` checks for a replica set. The result is stored in `self._change_streams_supported` and exposed via `supports_change_streams()`.

- **Collections created on success**:

  | Collection | Index / Special property |
  |---|---|
  | `fluidmcp_servers` | Unique index on `id` |
  | `fluidmcp_server_instances` | Index on `server_id` |
  | `fluidmcp_server_logs` | Capped (100 MB); compound index on `(server_name, timestamp)` |
  | `fluidmcp_llm_models` | Unique index on `model_id` |
  | `fluidmcp_llm_model_versions` | Compound index on `(model_id, archived_at DESC)` |
  | `fluidmcp_crash_events` | Compound index on `(server_id, timestamp)`; TTL index on `timestamp` (default 30 days) |

- **Connection pool defaults**: `maxPoolSize=50`, `minPoolSize=10`. Both are overridable via `FMCP_MONGODB_MAX_POOL_SIZE` / `FMCP_MONGODB_MIN_POOL_SIZE`. Write concern is `w="majority"` with `retryWrites=True`.

- **TLS**: certificate validation is enabled by default. Set `FMCP_MONGODB_ALLOW_INVALID_CERTS=true` only for development (logs a security warning).

---

## Interaction Summary

| Step | From | To | Call | Returns |
|---|---|---|---|---|
| 1 | `main()` | `connect_with_retry()` | `connect_with_retry(db_manager, max_retries=3, require_persistence)` | `True` / `False` / raises `RuntimeError` |
| 2 | `connect_with_retry()` | `DatabaseManager` | `await db_manager.init_db()` (per attempt) | `True` on success, `False` on failure |
| 3 | `DatabaseManager.connect()` | MongoDB | `AsyncIOMotorClient(uri, **options)` | Motor client handle |
| 4 | `DatabaseManager.connect()` | MongoDB | `await client.admin.command('ping')` | `{'ok': 1}` or raises `ConnectionFailure` |
| 5a | `DatabaseManager.connect()` | — | `self.db = client[database_name]` | database handle (local) |
| 5b | `DatabaseManager.connect()` | MongoDB | `await client.server_info()` then `replSetGetStatus` | version string / replica-set status |
| 5c | `DatabaseManager.init_db()` | MongoDB | `_migrate_collection_names()` — renames `servers`→`fluidmcp_servers` etc. if needed | — |
| 5d | `DatabaseManager.init_db()` | MongoDB | `create_index()` × 7 + `create_collection()` (capped) | — |
| 6 | `DatabaseManager` | `connect_with_retry()` | `return True` | — |
| 7 | `connect_with_retry()` | `main()` | `return True` | — |
| 8a | `DatabaseManager` | `connect_with_retry()` | `return False` (on exception) | — |
| 8b | `connect_with_retry()` | `main()` | `return False` (fallback) or `raise RuntimeError` (hard-exit) | — |
