# FluidMCP Debugging Tools — Implementation Plan

## Context

MCP servers on Railway (and codespace) experience:
- Unexpected crashes and restarts
- High-load MCPs starving others of resources
- Unclear root causes when something goes down

Both Railway and codespace use `fmcp serve` + MongoDB, so the same tooling applies to both environments.

---

## What Already Exists — Do Not Rebuild

### Process Tracking (server_manager.py)
- `server_manager.processes` — live `subprocess.Popen` handles per server
- `server_manager.start_times` — monotonic timestamps for uptime
- `server_manager._stderr_logs` — file handles for per-server stderr capture
- Auto-restart with exponential backoff; `restart_policy` / `max_restarts` config
- Memory limiting via `RLIMIT_AS` (enforced on spawn, not monitored)
- Idle cleanup: servers auto-stopped after `FMCP_IDLE_TIMEOUT` (default 1h)

### Crash Persistence (database.py + server_manager.py:1105–1154)
- `db.save_crash_event()` — writes to `fluidmcp_crash_events` MongoDB collection
- `db.list_crash_events(server_id, limit)` — queries crash history
- Fields stored per crash: `server_id`, `server_name`, `exit_code`, `stderr_tail` (last 2KB), `uptime_seconds`, `timestamp`
- TTL index: auto-deleted after 30 days (env: `FMCP_CRASH_EVENT_TTL_DAYS`)
- Stderr log files on disk: `~/.fluidmcp/logs/mcp_{server_id}_stderr.log` (10MB max, 5 rotations)

### Existing API Endpoints (management.py / run_servers.py)
- `GET /api/servers` — list all configured servers
- `GET /api/servers/{id}` — server config
- `GET /api/servers/{id}/status` — live process status (pid, state, uptime, exit_code)
- `GET /api/servers/{id}/logs` — DB-stored structured logs (not raw stderr)
- `POST /api/servers/{id}/start|stop|restart` — lifecycle control
- `GET /health` — overall health (running count, 200 vs 503)
- `GET /metrics` — Prometheus endpoint (auth-gated in secure mode)

### Prometheus Metrics Already Collected (metrics.py)
- `fluidmcp_requests_total` — by server, method, status
- `fluidmcp_request_duration_seconds` — histogram by server + method
- `fluidmcp_errors_total` — by server + error_category (5 categories)
- `fluidmcp_restarts_total` — by server + reason
- `fluidmcp_active_requests` — gauge by server
- `fluidmcp_server_status` — gauge: 0=stopped, 1=starting, 2=running, 3=error, 4=restarting
- `fluidmcp_uptime_seconds` — gauge by server
- System-wide only: process memory, system memory, open FDs — **NOT per-server**

---

## What's Missing — Prioritized by Debugging Value

### Priority 1: Crash Root Cause (Highest ROI)

**The problem:** `exit_code` is stored raw. No one knows that `137` = OOM-killed or `127` = binary not found. Crash events also don't capture what the server was doing when it died.

**What to build:**

**1a. Exit code classifier** — pure function, add to `server_manager.py`:
```
classify_exit(exit_code) -> { category, label, description }

0   → { "clean",    "clean_exit",          "Process exited normally" }
1   → { "error",    "generic_error",       "Unhandled error" }
126 → { "config",   "permission_denied",   "Cannot execute — check file permissions" }
127 → { "config",   "command_not_found",   "Binary/command not found — check command path" }
137 → { "resource", "oom_killed",          "Killed by OS (likely OOM) — check memory limits" }
139 → { "crash",    "segfault",            "Segmentation fault" }
143 → { "shutdown", "sigterm_container",   "SIGTERM from container runtime (Railway/Docker stop)" }
255 → { "error",    "unknown_fatal",       "Unknown fatal error — check stderr for details" }
-1  → { "resource", "killed_by_fluidmcp",  "Killed by FluidMCP resource monitor (OOM or CPU stuck)" }
-9  → { "resource", "sigkill",            "Force-killed (SIGKILL)" }
-15 → { "shutdown", "sigterm",            "Graceful shutdown (SIGTERM)" }
```

**1b. Resource snapshot at crash time** — the snapshot must be taken while the process is still alive. By the time `_cleanup_server()` runs, the PID is gone and `psutil` will throw `NoSuchProcess`.

The correct hook is `MCPHealthMonitor._check_server()` in `server_manager.py`. The detection point is:
```python
if process.poll() is not None:
    is_alive = False  # ← snapshot fires HERE, immediately after poll() confirms death
```

At this point the process has just been detected dead but `_cleanup_server()` has not been called yet. Try `psutil.Process(pid)` here; catch `NoSuchProcess` and fall back to the last cached snapshot (see below).

**Caching approach (handles the race reliably):** Add `_last_resource_snapshot: Dict[str, dict]` to `MCPHealthMonitor`. Every `_check_server()` cycle while the process is alive, update it via `psutil`. When death is detected, use whichever is available first — fresh read or last cached. This means the snapshot is at most 30 seconds stale (the health check interval), which is accurate enough.

Fields added to crash event:
- `memory_bytes_at_crash` — process RSS
- `cpu_percent_at_crash` — CPU % from last snapshot
- `active_requests_at_crash` — see note below

**Active requests at crash time:** Do NOT read this from the Prometheus gauge via `registry.get_metric()`. The `fluidmcp_active_requests` Gauge stores its values in `gauge.samples` (a plain dict keyed by label tuple). Read it directly:
```python
active_gauge = metrics_registry.get_metric("fluidmcp_active_requests")
key = active_gauge._get_label_key({"server_id": server_id})
active_at_crash = int(active_gauge.samples.get(key, 0))
```
This avoids a round-trip through the metrics render path during a crash cleanup. Alternatively, maintain a separate `Dict[str, int]` of active request counts directly in `ServerManager` if the metrics registry isn't easily accessible from the health monitor.

**1c. `GET /api/servers/{id}/crashes`** — expose `db.list_crash_events()` (DB layer already exists, just needs a route). Also include `restart_count` alongside crash history so you can triage "first crash in 3 days" vs "7th crash this hour":
```json
{
  "server": "my-mcp",
  "restart_count": 7,
  "crashes": [
    {
      "timestamp": "2026-04-30T14:23:01Z",
      "server_name": "my filesystem server",
      "exit_code": 137,
      "exit_category": "resource",
      "exit_label": "oom_killed",
      "exit_description": "Killed by OS (likely OOM) — check memory limits",
      "uptime_seconds": 143,
      "stderr_tail": "...",
      "memory_bytes_at_crash": 524288000,
      "cpu_percent_at_crash": 89.2,
      "active_requests_at_crash": 3
    }
  ]
}
```

`restart_count` comes from `MCPHealthMonitor._restart_counts[server_id]` (already tracked in memory) or from the instance state in MongoDB (`restart_count` field).

**Add `crashes_per_hour` to this response** — computed from the crash event timestamps already in MongoDB. Query the last hour's worth of events and count them:
```python
recent_crashes = [c for c in crashes if c["timestamp"] > now - 3600]
crashes_per_hour = len(recent_crashes)
```
Expose alongside `restart_count`. This is the flapping signal: a server with `crashes_per_hour: 12` needs immediate attention; one with `crashes_per_hour: 1` may be transient.

**Files to change:**
- `fluidmcp/cli/services/server_manager.py` — classifier function; snapshot in `MCPHealthMonitor._check_server()` at the `poll() is not None` detection point (~line 1532), not in `_cleanup_server()`
- `fluidmcp/cli/api/management.py` — add `GET /servers/{id}/crashes` route

---

### Priority 2: Per-Server Stderr Tail Endpoint

**The problem:** Stderr files exist on disk but there's no API to read them. The existing `GET /api/servers/{id}/logs` reads structured DB logs, not raw stderr. You currently need shell/SSH access to see what an MCP printed before crashing.

**What to build:**

`GET /api/servers/{id}/stderr?lines=50&contains=ERROR`
```json
{
  "server": "my-mcp",
  "file": "/root/.fluidmcp/logs/mcp_my-mcp_stderr.log",
  "lines": ["[ERROR] connect ECONNREFUSED 127.0.0.1:5432", "..."],
  "line_count": 12,
  "truncated": true
}
```

Reuse `server_manager._read_crash_stderr(id)` — it already reads from the on-disk rotated log file (`~/.fluidmcp/logs/mcp_{id}_stderr.log`) via `open()` + `seek(-max_bytes, SEEK_END)`, not from an in-memory buffer or the DB-stored 2KB tail. This means it works correctly for both running and dead servers.

Two changes needed vs the current implementation:
1. Accept a `lines` parameter instead of the fixed `max_bytes=2048` limit
2. Accept an optional `contains` query parameter — after reading N lines from disk, filter with `line for line in lines if contains.lower() in line.lower()`. Case-insensitive substring match is sufficient; no regex needed. Applied after the tail read, not during — keep the file I/O simple.

`line_count` in the response reflects how many lines matched (after filtering), not how many were read from disk. `truncated: true` means the log file had more lines than `?lines=` requested before filtering.

**Files to change:**
- `fluidmcp/cli/api/management.py` — add `GET /servers/{id}/stderr` route

---

### Priority 3: Per-Server Live Resource Snapshot

**The problem:** Prometheus has system-wide CPU/memory only. You can't tell which MCP is eating 800MB and whether it's approaching its limit.

**What to build:**

`GET /api/servers/{id}/resources`
```json
{
  "server": "my-mcp",
  "pid": 12345,
  "memory_rss_bytes": 524288000,
  "memory_rss_human": "500 MB",
  "memory_trend": "increasing",
  "cpu_percent": 23.4,
  "open_fds": 42,
  "threads": 8,
  "status": "running",
  "memory_limit_bytes": 1073741824,
  "memory_limit_human": "1 GB",
  "memory_usage_pct": 48.8
}
```

**`memory_trend`** is derived from the `_last_resource_snapshot` cache already maintained by `MCPHealthMonitor` (built in P1). Keep a short ring buffer of the last 3 RSS readings per server (`_memory_history: Dict[str, deque]`, maxlen=3). At read time:
- All values equal → `"stable"`
- Each value > previous → `"increasing"`
- Each value < previous → `"decreasing"`
- Mixed → `"fluctuating"`
- Fewer than 2 samples → `"unknown"`

This requires no new polling — values are populated as a side effect of the existing 30s health check cycle. The trend is a hint, not a guarantee; label it accordingly in docs.

Also extend Prometheus with per-server gauges (updated inside existing `MCPHealthMonitor` loop — no new polling thread needed):
- `fluidmcp_server_memory_rss_bytes{server_id="..."}`
- `fluidmcp_server_cpu_percent{server_id="..."}`
- `fluidmcp_server_open_fds{server_id="..."}`

**Files to change:**
- `fluidmcp/cli/api/management.py` — add `GET /servers/{id}/resources` route
- `fluidmcp/cli/services/metrics.py` — add 3 new per-server gauges (~line 375)
- `fluidmcp/cli/services/server_manager.py` — update gauges inside `MCPHealthMonitor._check_server()`

---

### Priority 4: Soft Resource Throttling + Kill Policy

**The problem:** Concurrency limits (P6) control request *flow*, but they don't stop a single MCP from consuming 99% of container memory or locking the CPU. On Railway, one container = shared CPU — a spiking MCP degrades every other MCP even with zero concurrent requests. This is the CEO's core concern.

**What to build:**

Add threshold checks to the existing `MCPHealthMonitor._check_server()` loop. Since the `_last_resource_snapshot` cache (built in P1) is already updated every 30s, this is two `if` blocks on data you already have.

**Memory kill policy:**
```python
mem_pct = snapshot["memory_usage_pct"]  # rss / memory_limit * 100

if mem_pct > memory_warn_pct:   # default 90%
    logger.warning(f"[RESOURCE] {server_id} memory at {mem_pct:.1f}% of limit")
    # also fires log-based alert (see P5 below)

if mem_pct > memory_kill_pct:   # default 98%
    logger.error(f"[RESOURCE] {server_id} memory at {mem_pct:.1f}%, killing to protect other servers")
    await self._sm._cleanup_server(server_id, exit_code=-1, reason="memory_limit_exceeded")
    # MCPHealthMonitor restart policy still applies after kill
```

**Kill loop protection** — without this, a misconfigured server kills and restarts in an infinite tight loop, burning Railway CPU. Add a per-server cooldown in `MCPHealthMonitor`:
```python
last_kill = self._last_kill_time.get(server_id)
if last_kill and (time.monotonic() - last_kill) < 60:
    logger.warning(f"[RESOURCE] {server_id} kill skipped — cooldown active ({60 - elapsed:.0f}s remaining)")
    return

self._last_kill_time[server_id] = time.monotonic()
# proceed with kill
```
`_last_kill_time: Dict[str, float]` — add to `MCPHealthMonitor.__init__`. 60s cooldown means at most one resource-triggered kill per minute per server. The existing `max_restarts` / exponential backoff already handles the restart side; this guard prevents the kill from firing again before the restart has had a chance to stabilise.
```

**CPU stuck policy** — a CPU spike that self-resolves is fine; a CPU lock that persists is a stuck process. Track consecutive high-CPU cycles:
```python
if cpu_pct > cpu_warn_pct:      # default 90%
    self._high_cpu_cycles[server_id] = self._high_cpu_cycles.get(server_id, 0) + 1
    if self._high_cpu_cycles[server_id] >= cpu_kill_cycles:   # default 3 cycles = ~90s
        logger.error(f"[RESOURCE] {server_id} CPU stuck at {cpu_pct:.1f}% for {cpu_kill_cycles} cycles, restarting")
        await self._sm._restart_server(server_id, reason="cpu_stuck")
        self._high_cpu_cycles.pop(server_id, None)
else:
    self._high_cpu_cycles.pop(server_id, None)  # reset on healthy cycle
```

**Config fields** (all optional, sensible defaults):
```json
{
  "memory_warn_pct": 90,
  "memory_kill_pct": 98,
  "cpu_warn_pct": 90,
  "cpu_kill_cycles": 3
}
```

If `memory_limit_bytes` is not set (no `RLIMIT_AS` configured), memory throttling is skipped — can't compute a percentage without a known limit. The `GET /api/servers/{id}/resources` endpoint should surface this explicitly:
```json
{ "memory_usage_pct": null, "memory_limit_note": "memory limit not configured — set FMCP_DEFAULT_MEMORY_LIMIT_MB to enable" }
```
Avoids silent confusion when an operator expects to see throttling but it's silently inactive.

**New Prometheus counter:** `fluidmcp_resource_kills_total{server_id, reason="memory_limit_exceeded"|"cpu_stuck"}`

**CPU percent warm-up** — `psutil.Process.cpu_percent()` returns `0.0` on the first call (it has no prior interval to compare against). If the first snapshot fires immediately after process spawn, the reading is garbage and could falsely trigger CPU stuck detection. Fix: call `proc.cpu_percent(interval=None)` once when first adding the process to `_last_resource_snapshot`, then discard the result. The second call (next health check cycle, 30s later) will be accurate.

**Files to change:**
- `fluidmcp/cli/services/server_manager.py` — threshold checks + `_high_cpu_cycles` dict + `_last_kill_time` dict in `MCPHealthMonitor._check_server()`; `reason` param on `_cleanup_server()` for the kill event; cpu_percent warm-up when process first registered
- `fluidmcp/cli/services/metrics.py` — add `fluidmcp_resource_kills_total` counter

---

### Priority 5: Log-Based Alerts

**The problem:** The system reacts to crashes (restarts them) but nothing flags *patterns*. A server that crashes 7 times in 10 minutes is a different problem than one that crashed once last week — but right now both look the same until you manually query `/crashes`.

**What to build:**

Lightweight `logger.warning()` calls woven into existing paths — no new infrastructure, no webhooks yet.

**Restart storm detection** — add to `MCPHealthMonitor._check_server()` after recording a restart:
```python
# Track timestamps of recent restarts in a sliding window
self._restart_timestamps[server_id].append(time.monotonic())
recent = [t for t in self._restart_timestamps[server_id] if t > now - 600]  # 10min window
self._restart_timestamps[server_id] = recent

if len(recent) >= 5:
    logger.warning(f"[ALERT] {server_id} has restarted {len(recent)} times in the last 10 minutes — marking unstable")
    await self._sm.db.update_instance_state(server_id, {"stability": "unstable"})
```

**Instability clears** when a server stays alive for > 10 minutes without restart — same place the existing `_restart_counts` reset happens.

**Resource warnings** — already included in P4 (`logger.warning` on memory_warn_pct / cpu_warn_pct).

**The `stability` field** surfaces in:
- `GET /api/servers/{id}/status` — add `"stability": "unstable"` to existing response
- `GET /api/servers/{id}/debug` (P7) — included in the aggregated view

**Future (out of scope for now):** Slack webhook, Railway log drain integration. The log lines are already structured enough to be picked up by Railway's log alerts if they set one up.

**Files to change:**
- `fluidmcp/cli/services/server_manager.py` — `_restart_timestamps` dict + alert check in `MCPHealthMonitor._check_server()`; `stability` field written to DB
- `fluidmcp/cli/repositories/database.py` — `update_instance_state()` must use `$set` (not a full document replace) so it only touches the `stability` field without clobbering crash history, config, or other instance state. Verify this before calling it from the health monitor.

---

### Priority 6: Concurrency Limiting + Visibility (Prevention)

> **Note:** This controls request *flow*, complementing the resource throttling in P4. Build after P4 since P4 is the more direct fix for Railway starvation.

**The problem:** No per-server request cap. A slow MCP under load queues dozens of requests, monopolizing the event loop and degrading all other MCPs.

**What to build:**

**6a. Per-server max concurrency config** — add optional field to server config:
```json
{ "max_concurrent_requests": 10 }
```
Enforced in `create_dynamic_router()` via a per-server `asyncio.Semaphore`.

**Drop vs queue decision (must decide before writing semaphore code):**
- **Drop immediately (recommended for now):** `asyncio.Semaphore.acquire()` with `asyncio.wait_for(..., timeout=0)` — returns 429 instantly. Simple, no queue buildup, callers know to retry. Correct for debugging purposes.
- **Queue with timeout:** `asyncio.wait_for(sem.acquire(), timeout=5.0)` — returns 429 only after 5s. More caller-friendly but means the event loop is held for up to 5s per queued request, which is exactly the starvation problem we're solving. **Avoid this initially.**

Default behavior: drop immediately with `Retry-After: 1` header. Can be made configurable via `"concurrency_queue_timeout": 0` in server config later.

**6b. `GET /api/servers/{id}/concurrency`** — live view:
```json
{
  "server": "my-mcp",
  "active_requests": 12,
  "max_concurrent": 10,
  "rejected_total": 5
}
```

**6c.** New Prometheus counter: `fluidmcp_requests_rejected_total{server_id, reason}` — use a `reason` label from the start, not hardcoded. Initial values: `"concurrency_limit"` (semaphore full), `"server_not_running"` (process dead at request time). Adding a new reason later is then a one-line change rather than a schema migration.

**Files to change:**
- `fluidmcp/cli/services/package_launcher.py` — semaphore in `create_dynamic_router()`
- `fluidmcp/cli/api/management.py` — add `GET /servers/{id}/concurrency` route
- `fluidmcp/cli/services/metrics.py` — add rejection counter

---

### Priority 7: `GET /api/servers/{id}/debug` — Single Pane of Glass

**The problem:** The individual endpoints (crashes, stderr, resources, concurrency) are all useful but require 4 separate API calls to triage one incident. When something is on fire, you want one request that shows everything.

**What to build:**

`GET /api/servers/{id}/debug` — aggregates all debug data in one response. Implementation is purely additive: call the same underlying functions that the individual endpoints use, no new data collection.

```json
{
  "server": "my-mcp",
  "snapshot_time": "2026-04-30T14:25:00Z",
  "status": {
    "state": "restarting",
    "pid": null,
    "uptime_seconds": null,
    "stability": "unstable"
  },
  "last_crash": {
    "timestamp": "2026-04-30T14:23:01Z",
    "server_name": "my filesystem server",
    "exit_code": 137,
    "exit_category": "resource",
    "exit_label": "oom_killed",
    "exit_description": "Killed by OS (likely OOM) — check memory limits",
    "uptime_seconds": 143,
    "memory_bytes_at_crash": 524288000,
    "cpu_percent_at_crash": 89.2,
    "active_requests_at_crash": 3
  },
  "crash_summary": {
    "total_crashes": 7,
    "crashes_last_10min": 3,
    "restart_count": 7
  },
  "current_resources": {
    "pid": null,
    "memory_rss_bytes": null,
    "memory_usage_pct": null,
    "cpu_percent": null,
    "open_fds": null,
    "note": "server not running"
  },
  "concurrency": {
    "active_requests": 0,
    "max_concurrent": 10,
    "rejected_total": 5
  },
  "stderr_tail": [
    "fatal error: runtime: out of memory",
    "goroutine 1 [running]:",
    "..."
  ]
}
```

Fields that can't be read (server dead, psutil unavailable, no crash history) return `null` with an optional `"note"` — never 500.

**Implementation:** Single route in `management.py` that calls `db.list_crash_events()`, `server_manager.get_status()`, the psutil read, the semaphore state, and `_read_crash_stderr()` — all with individual try/except so one failure doesn't blank the whole response. Each section should also be wrapped in `asyncio.wait_for(..., timeout=2.0)` so a hung DB call or a slow psutil read during an active incident doesn't cause the debug endpoint itself to time out. A debug endpoint that hangs when you need it most is worse than one that returns partial data quickly.

**Build order note:** The endpoint can be built as a skeleton after P1–P3 — fields for P4–P6 data (resources, concurrency, throttle kills) return `null` with `"note": "not yet available"` until those priorities are implemented. This makes `/debug` useful immediately after P3 and gives you an integration test harness as each priority lands. Do not wait for P6 to ship this.

**Files to change:**
- `fluidmcp/cli/api/management.py` — add `GET /servers/{id}/debug` route; build skeleton after P3, fill in remaining fields as P4–P6 land

---

## Implementation Order

| # | Deliverable | Value | Files |
|---|------------|-------|-------|
| 1 | Exit code classifier + crash resource snapshot | Closes ~80% of "why did it crash" questions | `server_manager.py` |
| 2 | `GET /api/servers/{id}/crashes` | Exposes existing crash DB data, no new storage | `management.py` |
| 3 | `GET /api/servers/{id}/stderr` | Raw stderr without shell access | `management.py` |
| 4 | `GET /api/servers/{id}/resources` | Identifies the resource hog | `management.py` |
| 5 | Per-server Prometheus gauges | Enables alerting and trends | `metrics.py`, `server_manager.py` |
| 6 | Resource throttling + kill policy | Directly prevents Railway starvation | `server_manager.py`, `metrics.py` |
| 7 | Log-based alerts + stability flag | Surfaces patterns, no new infra | `server_manager.py`, `database.py` |
| 8 | Concurrency cap + `GET /api/servers/{id}/concurrency` | Request-level protection | `package_launcher.py`, `management.py`, `metrics.py` |
| 9 | `GET /api/servers/{id}/debug` | Single pane of glass, ties everything together | `management.py` |

---

## Auth

All new endpoints follow the existing `management.py` pattern:
- No token in non-secure mode (local / codespace without `FMCP_SECURE_MODE`)
- Bearer token required when secure mode is on (Railway always sets this)
- Use existing `Depends(get_token)` at line 399 of `management.py`

---

## Codespace vs Railway

The core system is identical — both run `fmcp serve` + MongoDB, so all endpoints and monitoring apply to both. The difference is emphasis:

| | Codespace (dev) | Railway (prod) |
|---|---|---|
| Primary need | Crash debugging, stderr tails | Protection + stability signals |
| P1–P3 (crash root cause, stderr, resources) | Full value | Full value |
| P4 (resource kill policy) | Low priority — one dev, isolated | **Critical** — shared container CPU |
| P5 (log-based alerts) | Useful but not urgent | Important — catches flapping before it becomes an incident |
| P6 (concurrency limits) | Optional | Recommended for any high-traffic MCP |
| P7 (alerts + stability flag) | Nice to have | Should be on by default |
| P9 (`/debug` endpoint) | Convenient | The primary operational tool |

**Practical implication:** No separate code paths needed. The kill thresholds (P4) and alert thresholds (P5) are config-driven — set conservative defaults that are safe for dev, and tighten them via environment variables on Railway (`FMCP_MEMORY_KILL_PCT=98`, `FMCP_CPU_KILL_CYCLES=3`).

---

## Not Building (Out of Scope)

- Request correlation IDs / distributed tracing — too much scope
- Audit trail (who started/stopped what) — nice-to-have, not blocking debugging
- SSE-specific health metrics — edge case
- Dashboard UI — Prometheus + Grafana or existing `/docs` Swagger
