# fmcp serve — Startup Key Flow

> `fmcp serve` parses CLI flags, selects a persistence backend (MongoDB or in-memory), connects to the database with retry logic, creates the server manager and background tasks, builds the FastAPI app, restores saved LLM models, then hands control to Uvicorn.

**Key steps:** CLI Parse → Choose Backend → MongoDB Connect → Create ServerManager → Start Background Tasks → Build FastAPI App → Restore LLM Models → Start Uvicorn

## Flow Diagram

```
 START
   │
   ▼
┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│  1. CLI Parse        │     │  2. Choose Backend   │     │  3. MongoDB Connect  │     │  4. Create           │
│  cli.py              │────►│  server.py           │────►│  server.py           │────►│     ServerManager    │
│  main()              │     │  main()              │     │  connect_with_retry()│     │  server_manager.py   │
└──────────────────────┘     └──────────────────────┘     └──────────────────────┘     │  ServerManager.      │
                                                                                        │    __init__()        │
                                                                                        └──────────────────────┘
                                                                                                  │
                                                                                                  ▼
┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│  8. Start Uvicorn    │     │  7. Restore LLM      │     │  6. Build FastAPI    │     │  5. Start Background │
│  server.py           │◄────│     Models           │◄────│     App              │◄────│     Tasks            │
│  main()              │     │  server.py           │     │  server.py           │     │  server_manager.py   │
│  uvicorn.run()       │     │  load_models_from_   │     │  create_app()        │     │  start_idle_         │
└──────────────────────┘     │    persistence()     │     └──────────────────────┘     │    cleanup_task()    │
                             └──────────────────────┘                                  │  MCPHealthMonitor.   │
                                                                                        │    start()           │
                                                                                        └──────────────────────┘
   │
   ▼
 SERVING  (blocks on shutdown_event; SIGINT / SIGTERM triggers graceful teardown)
```

## Notes

- **`--require-persistence` flag**: If set, `connect_with_retry()` raises `RuntimeError` after 3 failed attempts and the server never starts. Without the flag, it logs a warning and continues in ephemeral (no-persistence) mode.
- **`--in-memory` / `--persistence-mode memory`**: Steps 3 (MongoDB Connect) is replaced by a trivial `InMemoryBackend.connect()` call; no network I/O or retry logic occurs.
- **Exponential backoff** in `connect_with_retry()`: waits 2 s after attempt 1, 4 s after attempt 2, then gives up after attempt 3.
- **Token handling**: If `--secure` is passed without `--token`, the CLI generates a `secrets.token_urlsafe(32)` token, prints it once to stdout, saves it to `~/.fmcp/tokens/current_token.txt` (mode 0o600), and exports it as `FMCP_BEARER_TOKEN`.
- **`--allow-insecure`** must be supplied explicitly if `--secure` is omitted; omitting both causes an immediate `sys.exit(1)` before any server code runs.
- **Background tasks** (Step 5) run as asyncio tasks (coroutines sharing the event loop) and are cancelled during graceful shutdown before the process exits.
- **Model restoration** (Step 7) is skipped entirely when `db_connected` is `False`; models are restored per-type: `replicate` clients are health-checked before registration; `vllm`/`ollama`/`lmstudio` processes are launched via `launch_single_llm_model()`.

## Step Summary

| Step | Name | File | Function | Role |
|------|------|------|----------|------|
| 1 | CLI Parse | `fluidmcp/cli/cli.py` | `main()` | `serve_parser` validates auth flags, generates token if needed, then calls `asyncio.run(server_main(args))` |
| 2 | Choose Backend | `fluidmcp/cli/server.py` | `main()` | Reads `--in-memory` / `--persistence-mode` flags; instantiates either `InMemoryBackend` or `DatabaseManager` |
| 3 | MongoDB Connect | `fluidmcp/cli/server.py` | `connect_with_retry()` | Attempts `db_manager.init_db()` up to 3 times with 2 s / 4 s / 8 s backoff; raises on failure if `--require-persistence` |
| 4 | Create ServerManager | `fluidmcp/cli/services/server_manager.py` | `ServerManager.__init__()` | Wires persistence backend; registers `atexit` cleanup hook for all child MCP processes |
| 5 | Start Background Tasks | `fluidmcp/cli/services/server_manager.py` | `start_idle_cleanup_task()` · `MCPHealthMonitor.start()` | Launches idle-server GC loop and crash-detection health monitor as asyncio tasks |
| 6 | Build FastAPI App | `fluidmcp/cli/server.py` | `create_app()` | Adds CORS, request-size middleware, mounts management/inspector/MCP routers, serves frontend static files |
| 7 | Restore LLM Models | `fluidmcp/cli/server.py` | `load_models_from_persistence()` | Reads saved model docs from MongoDB; re-initialises Replicate clients or relaunches vLLM/Ollama processes |
| 8 | Start Uvicorn | `fluidmcp/cli/server.py` | `main()` | Creates `uvicorn.Config` + `Server`, spawns `server.serve()` as an asyncio task, registers SIGINT/SIGTERM handlers, awaits shutdown event |
