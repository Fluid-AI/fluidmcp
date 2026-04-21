# EventLoopWatchdog & MCPHealthMonitor — Overview

**Target audience:** New developers joining the FluidMCP project
**Scope:** Two background monitors added for production stability — `EventLoopWatchdog` (asyncio lag detection) and `MCPHealthMonitor` (MCP process liveness + auto-restart)

---

## What Was Built

Two background monitors:

| Monitor | File | Purpose |
|---------|------|---------|
| `EventLoopWatchdog` | [`fluidmcp/cli/services/watchdog.py`](../../../fluidmcp/cli/services/watchdog.py) | Measures asyncio event loop lag — detects blocking calls |
| `MCPHealthMonitor` | [`fluidmcp/cli/services/server_manager.py`](../../../fluidmcp/cli/services/server_manager.py) | Polls MCP subprocess liveness — auto-restarts crashed servers |

> **Integration status:** `MCPHealthMonitor` is started automatically when `fmcp serve` runs (wired into `server.py`). `EventLoopWatchdog` is implemented and ready to use but is not yet wired into `server.py`.

---

## Architecture

```
+-------------------------------------------------------------------------+
|  fmcp serve  (server.py -- main() coroutine)                            |
|                                                                         |
|  +----------------------+    +--------------------------------------+   |
|  |  EventLoopWatchdog   |    |        MCPHealthMonitor              |   |
|  |  watchdog.py         |    |  server_manager.py                   |   |
|  |                      |    |                                      |   |
|  |  Background asyncio  |    |  Background asyncio task.            |   |
|  |  task -- measures    |    |  Polls every 30s. For each server:   |   |
|  |  sleep() drift       |    |    * stdio: process.poll()           |   |
|  |  every 10s.          |    |    * SSE: psutil check_process_alive |   |
|  |                      |    |    * if dead -> _cleanup_server()    |   |
|  |  lag > 0.5s -> WARN  |    |    * if restart policy allows ->     |   |
|  |  lag > 2.0s -> ERROR |    |      backoff delay -> restart        |   |
|  |                      |    |                                      |   |
|  |  (not yet wired into |    |                                      |   |
|  |   server.py)         |    |                                      |   |
|  +----------------------+    +--------------------------------------+   |
|             |                               |                           |
|             v                               v                           |
|       Loguru logger                   ServerManager                     |
|       (structured logs)               _cleanup_server() ->              |
|                                         db.save_crash_event()           |
|                                         db.save_instance_state()        |
+-------------------------------------------------------------------------+
```

---

## EventLoopWatchdog

### How it works

Every `_CHECK_INTERVAL` seconds the watchdog does:

```
before = time.monotonic()
await asyncio.sleep(_CHECK_INTERVAL)
lag = time.monotonic() - before - _CHECK_INTERVAL
```

If `lag` is large, the event loop was blocked during that sleep — a synchronous call, CPU-heavy coroutine, or I/O contention held the loop and prevented other tasks from running.

### Flow

```
watchdog._loop() starts
        |
        v
    record before = time.monotonic()
        |
        v
    await asyncio.sleep(10s)   <- yields control to event loop
        |
        v
    lag = wall_clock_delta - 10s
        |
        +-- lag >= 2.0s  ->  logger.error("Event loop lag Xs exceeds error threshold")
        +-- lag >= 0.5s  ->  logger.warning("Event loop lag Xs exceeds warn threshold")
        +-- lag < 0.5s   ->  (no log -- healthy)
        |
        v
    loop back
```

### Env vars

| Variable | Default | Meaning |
|----------|---------|---------|
| `FMCP_LOOP_LAG_WARN_S` | `0.5` | Log WARNING if lag exceeds this (seconds) |
| `FMCP_LOOP_LAG_ERROR_S` | `2.0` | Log ERROR if lag exceeds this (seconds) |
| `FMCP_LOOP_LAG_INTERVAL_S` | `10.0` | How often to measure (min: 0.001s) |

> All three are read at **module import time** via `_get_env_float()` and stored in module-level constants (`_WARN_THRESHOLD`, `_ERROR_THRESHOLD`, `_CHECK_INTERVAL`). Changing them at runtime has no effect.
>
> **Operator note:** There is no log warning when an invalid env value is silently discarded. For example, `FMCP_LOOP_LAG_WARN_S=0.5x` will silently fall back to the default `0.5`. Verify the correct threshold is active by checking startup logs where the watchdog prints its configured values.

### Safe env var parsing — `_get_env_float()`

```python
# watchdog.py
def _get_env_float(name, default, min_value=None):
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default          # bad value -> silent fallback
    if min_value is not None and value < min_value:
        return default          # below min -> fallback
    return value
```

> Called at **module import time** (to set `_WARN_THRESHOLD` etc.), so it must NOT call `logger` — loguru may not be configured yet.

### Lifecycle

```python
watchdog = EventLoopWatchdog()
watchdog.start()   # creates asyncio.Task, guards against duplicate start
...
await watchdog.stop()  # cancels task, awaits CancelledError, sets _task = None
```

---

## MCPHealthMonitor

### How it works

Every `check_interval` seconds (default 30s, overridden by `FMCP_HEALTH_CHECK_INTERVAL` env var) the monitor iterates all running MCP server processes and checks liveness:

- **stdio servers** (`subprocess.Popen`): `process.poll()` — non-None return means the process has exited
- **SSE servers** (`SseSubprocessHandle`): `health_checker.check_process_alive(pid)` via psutil

### Flow

```
_monitor_loop() runs every 30s
        |
        v
    snapshot = list(server_manager.processes.items())
        |
        v
    for each (server_id, process):
        |
        v
    _check_server(server_id, process)
        |
        +-- stdio: process.poll() is None  ->  alive
        +-- SSE:   check_process_alive()   ->  alive
        |
        +-- process has exited
                |
                v
            already in _restarts_in_progress?  ->  skip (no duplicate)
                |
                v
            get config from DB
                |
                +-- config missing  ->  _cleanup_server() only, no restart
                |
                +-- config found
                        |
                        v
                    restart_policy == "never"?  ->  cleanup only
                        |
                        v
                    restart_policy == "on-failure" and exit_code == 0?  ->  cleanup only
                        |
                        v
                    restart_count >= max_restarts?
                        ->  cleanup only, log warning
                        ->  server stays stopped until operator manually restarts via API
                        |
                        v
                    calculate backoff delay
                    await asyncio.sleep(delay)
                        |
                        v
                    acquire op_lock
                    _cleanup_server(server_id, exit_code)
                    asyncio.wait_for(_start_server_unlocked(), timeout=60s)  <- FMCP_RESTART_TIMEOUT_S
                        |
                        +-- success  ->  log info, increment restart_count
                        +-- timeout  ->  log error, increment restart_count
                        +-- failure  ->  log error, increment restart_count
        |
        v
    await asyncio.sleep(check_interval)
```

### Restart count reset

The restart count for a server resets only after **5 minutes of sustained healthy uptime** (checked on the next poll cycle where the process is still alive). This prevents a flapping server from getting a "fresh start" too soon and exhausting `max_restarts` across many short-lived restart cycles.

### After max_restarts is hit

Once `restart_count >= max_restarts`, the monitor stops attempting restarts. The server process stays stopped. **An operator must manually restart it** via the management API:

```bash
curl -X POST http://localhost:<port>/api/servers/<server_id>/start \
  -H "Authorization: Bearer <token>"
```

The restart count does not automatically reset — the server will not self-recover without manual intervention.

### Env vars

| Variable | Default | Meaning |
|----------|---------|---------|
| `FMCP_HEALTH_CHECK_INTERVAL` | `30` | Seconds between health-check polls (integer) |
| `FMCP_RESTART_TIMEOUT_S` | `60` | Seconds before a single restart attempt is cancelled |

### Exponential backoff

```
delay = 5s x 2^min(restart_count, 5)

restart 0 ->   5s
restart 1 ->  10s
restart 2 ->  20s
restart 3 ->  40s
restart 4 ->  80s
restart 5+ -> 160s  (maximum)
```

### Restart policies

| Policy | Behaviour |
|--------|-----------|
| `"on-failure"` | Restart only on non-zero exit code (default when field is omitted) |
| `"always"` | Restart on any exit (including exit 0) |
| `"never"` | No automatic restart |

---

## Startup & Shutdown Integration (`server.py`)

`MCPHealthMonitor` is integrated into `server.py`. The current startup order is:

```python
# server.py -- main()

# 1. Start health monitor BEFORE create_app()
health_monitor = MCPHealthMonitor(server_manager, check_interval=health_check_interval)
health_monitor.start()

# 2. Create FastAPI app
app = await create_app(...)

# ... server runs until shutdown signal ...

# 3. Shutdown order
await health_monitor.stop()                    # stop monitor first
await server_manager.stop_idle_cleanup_task()  # stop idle cleanup
await server_manager.shutdown_all()            # stop all MCP processes last
```

> `EventLoopWatchdog` is not yet wired into `server.py`. The class is ready in `watchdog.py` and can be added to the lifecycle above when needed.

---

## Key Files

| File | Role |
|------|------|
| [`fluidmcp/cli/services/watchdog.py`](../../../fluidmcp/cli/services/watchdog.py) | `EventLoopWatchdog` + `_get_env_float()` |
| [`fluidmcp/cli/services/server_manager.py`](../../../fluidmcp/cli/services/server_manager.py) | `MCPHealthMonitor` + `_check_server()` + `_calculate_restart_delay()` |
| [`fluidmcp/cli/server.py`](../../../fluidmcp/cli/server.py) | `MCPHealthMonitor` start/stop integration in `main()` |
| [`tests/test_server_manager_cleanup.py`](../../../tests/test_server_manager_cleanup.py) | Tests for `ServerManager` shutdown and process cleanup |
