# EventLoopWatchdog & MCPHealthMonitor — Overview

**Target audience:** New developers joining the FluidMCP project
**Scope:** Two background monitors added for production stability — `EventLoopWatchdog` (asyncio lag detection) and `MCPHealthMonitor` (MCP process liveness + auto-restart)

---

## What Was Built

Two background monitors:

| Monitor | File | Status |
|---------|------|--------|
| `EventLoopWatchdog` | [`fluidmcp/cli/services/watchdog.py`](../../../fluidmcp/cli/services/watchdog.py) | Implemented — not yet merged to main, not yet wired into `server.py` |
| `MCPHealthMonitor` | [`fluidmcp/cli/services/server_manager.py`](../../../fluidmcp/cli/services/server_manager.py) | Implemented and wired into `server.py` |

> **Note on EventLoopWatchdog:** The implementation exists on feature branches but has not yet merged to `main`. The sections below document what was built. Once merged, it can be wired into `server.py` following the same lifecycle pattern as `MCPHealthMonitor`.

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
|  |  every 10s.          |    |    * SSE: HealthChecker              |   |
|  |                      |    |      .check_process_alive(pid)       |   |
|  |  lag > 0.5s -> WARN  |    |      (uses psutil internally)        |   |
|  |  lag > 2.0s -> ERROR |    |    * if dead -> acquire op_lock      |   |
|  |                      |    |      -> _cleanup_server()            |   |
|  |  (not yet on main /  |    |    * if restart policy allows ->     |   |
|  |   not yet wired into |    |      backoff delay -> restart        |   |
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

> **Status:** Implementation exists on feature branches, not yet merged to `main`.

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

Every `check_interval` seconds (default 30s, overridden by `FMCP_HEALTH_CHECK_INTERVAL` env var) the monitor iterates all running MCP server processes and checks liveness. An additional env var `FMCP_RESTART_TIMEOUT_S` (default 60s) controls how long a restart attempt is allowed to run before it is cancelled:

- **stdio servers** (`subprocess.Popen`): `process.poll()` — non-None return means the process has exited
- **SSE servers** (`SseSubprocessHandle`): `HealthChecker.check_process_alive(pid)` — a wrapper around psutil that checks the process is alive by PID

### Restart count — in-memory vs database

`MCPHealthMonitor` tracks restart attempts in `self._restart_counts` — an **in-memory dict** keyed by `server_id`. This is separate from any `restart_count` stored in the database instance state. The in-memory count is used solely to enforce `max_restarts` within the lifetime of the current monitor. It resets to zero (for a given server) after 5 minutes of sustained healthy uptime, or when the monitor process restarts.

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
        +-- SSE:   HealthChecker.check_process_alive()  ->  alive
        |
        +-- process has exited
                |
                v
            already in _restarts_in_progress?  ->  skip (no duplicate)
                |
                v
            get config from DB
                |
                +-- config missing
                |     acquire op_lock
                |     _cleanup_server() only, no restart
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
                    _restart_counts[server_id] >= max_restarts?
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
                        +-- success  ->  log info, increment _restart_counts[server_id]
                        +-- timeout  ->  log error, increment _restart_counts[server_id]
                        +-- failure  ->  log error, increment _restart_counts[server_id]
        |
        v
    await asyncio.sleep(check_interval)
```

### Restart count reset

The in-memory `_restart_counts[server_id]` resets only after **5 minutes of sustained healthy uptime** (checked on the next poll cycle where the process is still alive). This prevents a flapping server from getting a "fresh start" too soon and exhausting `max_restarts` across many short-lived restart cycles.

### After max_restarts is hit

Once `_restart_counts[server_id] >= max_restarts`, the monitor stops attempting restarts. The server process stays stopped. **An operator must manually restart it** via the management API:

```bash
curl -X POST http://localhost:<port>/api/servers/<server_id>/start \
  -H "Authorization: Bearer <token>"
```

The in-memory restart count does not automatically reset — the server will not self-recover without manual intervention.

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

`MCPHealthMonitor` is integrated into `server.py`. The complete startup and shutdown order:

```python
# server.py -- main()

# 1. Create ServerManager
server_manager = ServerManager(persistence)

# 2. Start idle cleanup task
server_manager.start_idle_cleanup_task()

# 3. Start health monitor
health_monitor = MCPHealthMonitor(server_manager, check_interval=health_check_interval)
health_monitor.start()

# 4. Create FastAPI app
app = await create_app(...)

# ... server runs until shutdown signal ...

# 5. Shutdown order
await health_monitor.stop()                    # stop monitor first
await server_manager.stop_idle_cleanup_task()  # stop idle cleanup
await server_manager.shutdown_all()            # stop all MCP processes
await persistence.disconnect()                 # close DB connection last
```

> `EventLoopWatchdog` is not yet wired into `server.py`. Once `watchdog.py` is merged to `main`, it can be added between steps 3 and 4, with `await loop_watchdog.stop()` added to the shutdown sequence after `health_monitor.stop()`.

---

## Key Files

| File | Role |
|------|------|
| [`fluidmcp/cli/services/watchdog.py`](../../../fluidmcp/cli/services/watchdog.py) | `EventLoopWatchdog` + `_get_env_float()` (not yet on main) |
| [`fluidmcp/cli/services/server_manager.py`](../../../fluidmcp/cli/services/server_manager.py) | `MCPHealthMonitor` + `_check_server()` + `_calculate_restart_delay()` |
| [`fluidmcp/cli/server.py`](../../../fluidmcp/cli/server.py) | `MCPHealthMonitor` start/stop integration in `main()` |
| [`tests/test_server_manager_cleanup.py`](../../../tests/test_server_manager_cleanup.py) | Tests for `ServerManager` shutdown and process cleanup |
