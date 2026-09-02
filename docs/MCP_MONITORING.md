# MCP Fleet Monitoring

How FluidMCP detects, recovers from, and reports MCP server failures — and how an
external monitoring system consumes that.

**Audience:** both the FluidMCP team and whoever builds the monitoring/alerting
side. Sections 1–4 are the concepts and the API; §5–6 are for the consumer; §7–9
are operational.

> Scope note: this document covers **MCP server health monitoring**. For
> Prometheus metrics and Grafana dashboards see [MONITORING.md](MONITORING.md)
> and [MONITORING_SETUP.md](MONITORING_SETUP.md); for LLM inference metrics see
> [OBSERVABILITY.md](OBSERVABILITY.md).

---

## Table of contents

1. [The three failure classes](#1-the-three-failure-classes)
2. [Architecture](#2-architecture)
3. [What FluidMCP does on its own](#3-what-fluidmcp-does-on-its-own)
4. [API reference](#4-api-reference)
5. [Consuming it from a monitoring system](#5-consuming-it-from-a-monitoring-system)
6. [Alerting and dashboards](#6-alerting-and-dashboards)
7. [Configuration](#7-configuration)
8. [Production deployment](#8-production-deployment)
9. [Testing and acceptance](#9-testing-and-acceptance)
10. [Implementation notes](#10-implementation-notes)

---

## 1. The three failure classes

These are genuinely different problems and need different responses. Conflating
them is the single most common mistake in MCP monitoring.

| Class | Example | How FluidMCP sees it | Does a restart fix it? |
|---|---|---|---|
| **Process death** | OOM kill, segfault, crash on boot | PID gone → `server.crashed` | Usually yes — automatic |
| **Zombie** | Process alive, HTTP hung | ping timeout → `server.zombie` | Usually yes — automatic |
| **Dependency failure** | SQL connection broken, expired credential | Process perfectly healthy; **tool calls fail** | **No — needs a human** |

### Why the third class is the hard one

> **A broken database connection does not kill the process.**

Every process-level health check answers *"is it alive and serving HTTP?"* For an
MCP whose database credentials expired, whose connection pool is exhausted, or
whose upstream is 503-ing, the answer is **yes** — PID alive, HTTP answering,
`tools/list` fine. A process watchdog sees a healthy server while every user
request fails.

That failure is only visible in three places:

1. **Tool results** — a JSON-RPC `error`, or (more often) a **200 OK result with
   `isError: true`** carrying text like `ECONNREFUSED 10.20.1.44:1433`. Treating
   `isError` responses as successes is the easiest way to under-report real
   failures.
2. **stderr** — the MCP's own logging.
3. **Latency** — pool exhaustion shows up as timeouts before it shows up as errors.

FluidMCP therefore runs three detectors alongside the process watchdog:

- **Passive** — per-`(server, tool)` rolling error rates from live traffic.
- **Active** — an optional `health_probe` that calls one cheap tool on a timer.
  This is the *only* way to catch a broken dependency on an **idle** server,
  which is exactly the 3am case.
- **Classification** — a pattern catalog over tool errors and stderr that names
  the failure *and assigns an owner*.

### Owner attribution

Every classified failure carries `failure_owner`, which is what makes a report
actionable rather than a finger-pointing exercise:

| Owner | Meaning | Route to |
|---|---|---|
| `customer` | Credentials, firewall, database config | The customer's own team |
| `fluidmcp` | Our bug, our packaging, our resource limits | FluidMCP oncall |
| `external` | Upstream vendor outage, rate limiting | Usually wait; inform |
| `unknown` | Unrecognised signature | FluidMCP oncall to triage |

---

## 2. Architecture

```
┌─────────────────────────── FluidMCP gateway ───────────────────────────┐
│                                                                        │
│  MCPHealthMonitor ──┐                                                  │
│  ToolErrorTracker ──┼──► EventBus ──┬──► MongoDB (mcp_events, TTL 30d) │
│  DependencyProbe  ──┤               ├──► SSE  /api/monitoring/stream   │
│  ResourceMonitor  ──┘               └──► WebhookDispatcher (HMAC)      │
│                                                                        │
│  FailureClassifier ──► failure_category + owner + remediation          │
│  ConfigValidator   ──► missing / placeholder credentials, pre-flight   │
│  GatewayInfo       ──► boot_id, config validity, self-resources        │
└────────────────────────────────────────────────────────────────────────┘
            │ push (webhook, <1s)          ▲ pull (poll 30s, backstop)
            ▼                              │
┌───────────────────── external monitoring system ───────────────────────┐
│  Collector → State store → Alert engine → Dashboards + reports         │
└────────────────────────────────────────────────────────────────────────┘
```

**Division of responsibility.** FluidMCP owns process state, restart policy,
failure classification, and event emission. It is the source of truth and it
self-heals. The monitoring system owns long-term history, alert routing,
dashboards, SLA reports, and aggregation across deployments.

FluidMCP does **not** send email or Slack. It emits typed events; the monitoring
system decides who hears about them.

**Both push and pull are required.** Webhooks give sub-second crash alerts.
Polling is the backstop:

> **If FluidMCP itself dies, zero webhooks fire.** Silence is indistinguishable
> from "everything is healthy" unless something is actively polling. A failed or
> stale poll must be the monitoring system's highest-severity alert.

---

## 3. What FluidMCP does on its own

### 3.1 The watchdog

[`MCPHealthMonitor`](../fluidmcp/cli/services/server_manager.py) runs every
`FMCP_HEALTH_CHECK_INTERVAL` seconds (default 30) over every managed process:

- **PID liveness** via `psutil`, catching zombie and dead states.
- **Zombie detection** for HTTP-transport servers — POSTs `tools/list` with a
  `FMCP_HTTP_PING_TIMEOUT` (default 10s). PID alive but no HTTP response is
  treated as dead.
- **Resource snapshot** each cycle (RSS, CPU%, active requests) with a 3-sample
  memory ring for trend detection.
- **Threshold enforcement** — kills at `FMCP_MEMORY_KILL_PCT` (98%), warns at
  `FMCP_MEMORY_WARN_PCT` (90%), restarts after `FMCP_CPU_KILL_CYCLES` (3)
  consecutive cycles above `FMCP_CPU_WARN_PCT` (90%). 60s kill cooldown.
- **Restart under policy** with exponential backoff (`5s × 2^min(count,5)`),
  capped by the server's `max_restarts`.
- **Restart-storm detection** — ≥`FMCP_RESTART_STORM_THRESHOLD` (5) restarts in
  10 minutes flips `stability` to `unstable`. Cleared after 5 minutes healthy.
- **Degradation check** — per-tool error rates (§3.3).
- **Dependency probe** — if configured (§3.4).

### 3.2 Crash forensics

Every non-intentional exit persists a crash event with exit-code classification,
stderr tail, uptime, and the resource snapshot taken just before death:

```json
{
  "server_id": "pids",
  "exit_code": 137,
  "exit_category": "resource",
  "exit_label": "oom_killed",
  "exit_description": "Killed by OS (likely OOM) — check memory limits",
  "stderr_tail": "...",
  "uptime_seconds": 412.5,
  "memory_bytes_at_crash": 1073741824,
  "timestamp": "2026-09-01T10:14:02Z"
}
```

### 3.3 Per-tool error tracking

Tracked per `(server_id, tool_name)`, not only per server. **A server-wide
average cannot catch one broken endpoint**: a tool failing 100% of the time
inside a server whose other tools are healthy might sit at 12% overall and never
cross a threshold. Both views are exposed — per-tool rates drive alerts, the
server-wide rate gives context.

- **Degraded** when any single tool's error rate ≥ `FMCP_DEGRADED_ERROR_RATE`
  (0.5) over ≥ `FMCP_DEGRADED_MIN_SAMPLES` (5) calls, or the server-wide rate
  crosses the same threshold.
- **Recovered** when no tool is failing *and* `FMCP_RECOVERY_STREAK` (5)
  consecutive successes have followed. Recovery is streak-based rather than
  rate-based on purpose: rate-based recovery is pathologically sticky, because
  the historical failures stay inside the window and keep a demonstrably-working
  server flagged for minutes.

Outcomes counted as failures: `error`, `tool_error` (an `isError: true` result),
`timeout`, `parse_error`.

### 3.4 Active dependency probing

Opt-in per server. Catches a broken dependency on an idle server, which no
passive signal can see:

```json
{
  "id": "pids",
  "command": "python3",
  "args": ["pids_server.py"],
  "health_probe": {
    "tool": "get_latest_alarms",
    "args": { "since_id": 0, "limit": 1 },
    "interval_seconds": 60,
    "timeout_seconds": 25,
    "failure_threshold": 2
  }
}
```

Runs inside the existing watchdog cycle — no second scheduler. The probe tool
must be cheap and side-effect-free.

**A dependency failure does not trigger a restart by default.** Restarting
rarely fixes wrong credentials, and a restart loop actively hides the fault.
Opt in with `"restart_on_dependency_failure": true` — appropriate for
connection-pool leaks, where a restart genuinely does help.

### 3.5 Pre-flight config validation

Before spawning, FluidMCP checks:

- **declared `required_env`** — present and non-empty
- **placeholder values** — `<your-key>`, `xxxxxx`, `your-...`, `changeme`
- **unresolved interpolation** — a surviving `${VAR}` means the variable was never set
- **command reachability** — `shutil.which(command)`, so a missing binary is
  reported as a config error rather than surfacing later as exit 127

Findings emit `server.config_invalid` with the offending **key names only —
never values**.

Default behaviour is **warn-and-start**, not block: a server may legitimately
read credentials from a mounted file, and refusing to start would turn a
monitoring feature into an outage. Set `"strict_config": true` per server (or
`FMCP_STRICT_CONFIG=true` globally) to refuse instead.

### 3.6 Gateway self-monitoring

Everything above monitors the MCP servers. This monitors **FluidMCP itself** —
the case where the container is redeployed with a bad Mongo URI or a missing
bearer token and answers health checks while being functionally broken.

- **`boot_id`** — generated once per process, included in every payload. A
  changed `boot_id` between polls is unambiguous proof the gateway restarted,
  which is what separates a deploy from a crash from a network blip. It is also
  the authoritative signal that the event `seq` counter has reset.
- **`boot_count`** — cumulative boots for this `gateway_id`. Jumping by more
  than 1 between polls means a crash loop.
- **Config validity on `/health`** — reported on the **unauthenticated**
  endpoint by design: if the bearer token is the thing that is missing, a
  monitoring system cannot authenticate to find out why every `/api` call
  returns 500.
- **Liveness vs readiness** — `/health` answers 200 whenever the process is
  serving, *including when misconfigured*; `/health/ready` returns 503 until
  dependencies are usable. Conflating them makes a broken-but-running container
  indistinguishable from a dead one.
- **Event-loop lag** — the highest-signal gateway metric. A blocked loop stops
  the gateway answering everything, including its own health checks, and is
  invisible in CPU and memory figures.

---

## 4. API reference

Base URL is the gateway root. All `/api/*` routes require
`Authorization: Bearer <FMCP_BEARER_TOKEN>` when `FMCP_SECURE_MODE=true`.
`/health` and `/health/ready` are always unauthenticated.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness + boot identity + config validity |
| `GET` | `/health/ready` | Readiness (503 until dependencies usable) |
| `GET` | `/api/monitoring/health` | **Fleet rollup — primary poll target** |
| `GET` | `/api/monitoring/gateway` | Gateway self-health, self-resources, bus stats |
| `GET` | `/api/monitoring/events` | Incremental event feed (`seq` cursor) |
| `GET` | `/api/monitoring/stream` | SSE live event push |
| `GET` | `/api/monitoring/servers/{id}/diagnosis` | Why is this server failing |
| `GET` | `/api/monitoring/uptime` | Uptime %, MTTR, MTBF per server |
| `GET` | `/api/monitoring/event-types` | Enumerate event types + default severities |
| `POST` | `/api/monitoring/webhooks` | Register a push receiver |
| `GET` | `/api/monitoring/webhooks` | List receivers (secrets redacted) |
| `DELETE` | `/api/monitoring/webhooks/{id}` | Remove a receiver |
| `POST` | `/api/monitoring/webhooks/{id}/test` | Send a synthetic delivery |
| `POST` | `/api/monitoring/webhooks/{id}/enable` | Re-enable an auto-disabled receiver |

Pre-existing endpoints that remain useful:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/servers` | Server list with nested status |
| `GET` | `/api/servers/{id}/debug` | Per-server aggregator |
| `GET` | `/api/servers/{id}/crashes` | Crash history |
| `GET` | `/api/servers/{id}/stderr?lines=&contains=` | Raw log tail |
| `POST` | `/api/servers/{id}/restart` \| `start` \| `stop` | Lifecycle control |

### 4.1 `GET /health`

```json
{
  "status": "healthy",
  "gateway_id": "gw-prod-1",
  "boot_id": "boot_01J8X7QK...",
  "boot_count": 47,
  "started_at": "2026-09-01T08:00:11Z",
  "uptime_seconds": 8031,
  "config": {
    "valid": false,
    "errors": [
      { "key": "FMCP_BEARER_TOKEN",
        "problem": "not set while FMCP_SECURE_MODE=true",
        "impact": "all /api requests will return HTTP 500" }
    ],
    "warnings": []
  },
  "database": { "status": "connected", "persistence_enabled": true },
  "version": "2.0.0"
}
```

`status`: `healthy` | `degraded` | `starting`. **`config.errors` non-empty is a
P1 regardless of `status`** — the gateway is up but broken.

### 4.2 `GET /api/monitoring/health` — fleet rollup

One call, every server. This is the primary polling endpoint; it serves from
in-memory state plus one database read.

```json
{
  "gateway_id": "gw-prod-1",
  "boot_id": "boot_01J8X7QK...",
  "generated_at": "2026-09-01T10:14:02.113Z",
  "gateway": {
    "status": "healthy", "uptime_seconds": 84213,
    "database": "connected", "config_valid": true,
    "health_monitor_running": true
  },
  "summary": {
    "total": 3, "running": 1, "degraded": 1, "failed": 0,
    "stopped": 0, "config_error": 1, "unstable": 0,
    "dependency_failed": 0, "crashes_last_hour": 3
  },
  "servers": [
    {
      "id": "pids",
      "name": "PIDS Analytics MCP",
      "state": "degraded",
      "process_state": "running",
      "pid": 4412,
      "uptime_seconds": 3600,
      "restart_count": 2,
      "stability": "stable",
      "transport": "stdio",
      "memory_rss_bytes": 268435456,
      "memory_usage_pct": 25.6,
      "memory_trend": "rising",
      "cpu_percent": 3.1,
      "active_requests": 0,
      "error_rate_5m": 0.83,
      "calls_5m": 6,
      "success_streak": 0,
      "failing_tools": [
        { "tool": "get_latest_alarms", "calls": 6, "errors": 5,
          "error_rate_5m": 0.83,
          "last_error": "ECONNREFUSED 10.20.1.44:1433" }
      ],
      "config_issues": { "missing_env": [], "placeholder_env": [], "unresolved_env": [] },
      "dependency_failed": false,
      "consecutive_failures": 0,
      "failure_category": "db_connection_refused",
      "failure_owner": "customer",
      "last_error": "ECONNREFUSED 10.20.1.44:1433",
      "last_crash": { "timestamp": "2026-09-01T09:02:11Z",
                      "exit_code": 137, "exit_label": "oom_killed" }
    }
  ]
}
```

#### `state` — the field that drives status colours

| State | Meaning | Dashboard |
|---|---|---|
| `running` | Alive and serving | 🟢 |
| `degraded` | Alive, but tool calls are failing | 🟠 **alert a human** |
| `config_error` | Missing/placeholder credentials, or bad command | 🟠 **customer must fix** |
| `restarting` | Mid-restart | 🟡 |
| `failed` | Dead; restart exhausted or failed | 🔴 |
| `stopped` | Intentionally stopped, or never started | ⚪ |

`process_state` is the **raw** process state, kept alongside so a consumer can
still see that the process is fine while `state` says `degraded`. That contrast
is the whole point: `process_state: running` + `state: degraded` is a dependency
failure.

#### Other fields worth understanding

**`stability: "unstable"`** is orthogonal to `state` — it means ≥5 restarts in
10 minutes. A server can be `running` **and** `unstable`. That combination is a
**crash loop**: it looks fine on any single poll and is one of the
highest-signal conditions on the dashboard. Do not let `running` mask it.

**`failing_tools[]`** — drive per-endpoint alerts off this array, not off
`error_rate_5m`, or a single broken endpoint inside a busy server will never
trip a threshold.

**`success_streak`** — consecutive successes at the tail of the window, across
all of the server's tools. A degraded server clears at
`FMCP_RECOVERY_STREAK` (5). Treat a rising streak on a degraded server as
"recovering".

**`config_issues`** — key **names** only; values are never returned.

### 4.3 `GET /api/monitoring/gateway`

```json
{
  "gateway_id": "gw-prod-1",
  "boot_id": "boot_01J8X7QK...",
  "boot_count": 47,
  "status": "degraded",
  "config": { "valid": false, "errors": [...], "warnings": [...] },
  "database": { "connected": true, "persistence_enabled": true },
  "resources": {
    "memory_rss_bytes": 412386304, "memory_rss_human": "393.3 MB",
    "cpu_percent": 6.2, "open_fds": 214, "threads": 18,
    "event_loop_lag_ms": 12
  },
  "servers_managed": 12,
  "health_monitor": { "running": true, "check_interval_seconds": 30 },
  "event_bus": { "latest_seq": 10437, "buffered": 1000, "dropped_persist": 0 },
  "webhooks": { "receivers": 1, "delivered": 842, "failed": 3 },
  "recent_boots": [...]
}
```

`event_loop_lag_ms` above ~250 means the gateway is blocked and will start
failing everything, including its own health checks.

### 4.4 `GET /api/monitoring/events`

```
GET /api/monitoring/events?since=10432&limit=100&severity=warning&server_id=pids&type=server.crashed
```

| Param | Notes |
|---|---|
| `since` | Last `seq` processed, **exclusive**. Omit for the most recent `limit`. |
| `limit` | 1–500, default 100 |
| `severity` | `info` \| `warning` \| `critical` — this level **and above** |
| `server_id` | Filter to one server |
| `type` | Filter to one event type |

```json
{
  "gateway_id": "gw-prod-1",
  "boot_id": "boot_01J8X7QK...",
  "generated_at": "2026-09-01T10:14:02Z",
  "latest_seq": 10437,
  "returned": 1,
  "events": [
    {
      "event_id": "evt_01J8X...",
      "seq": 10433,
      "type": "server.crashed",
      "severity": "critical",
      "gateway_id": "gw-prod-1",
      "boot_id": "boot_01J8X7QK...",
      "server_id": "pids",
      "server_name": "PIDS Analytics MCP",
      "timestamp": "2026-09-01T10:13:58.442Z",
      "data": {
        "exit_code": 137,
        "exit_label": "oom_killed",
        "uptime_seconds": 412.5,
        "stderr_tail": "...",
        "failure_category": "oom",
        "failure_owner": "fluidmcp",
        "summary": "The MCP server was killed for exceeding its memory budget.",
        "remediation": "Raise memory_limit_mb or investigate the memory leak.",
        "restart_would_help": true
      }
    }
  ]
}
```

**Cursor rules.** `seq` is a gap-free monotonic counter **per gateway boot**:

- Persist `latest_seq` after each batch and pass it back as `since`.
- Key the cursor on **`(gateway_id, boot_id)`**. `seq` restarts at 1 on every
  boot, so a changed `boot_id` means reset the cursor to 0 and re-sync.
- `events[0].seq > cursor + 1` means you missed events; they are still in the
  database — re-request from your cursor.
- **Never use timestamps as a cursor.** Clock skew and same-millisecond writes
  cause silent loss.

### 4.5 `GET /api/monitoring/stream` — SSE

```
Accept: text/event-stream

event: connected
data: {"gateway_id":"gw-prod-1","boot_id":"boot_...","latest_seq":10437}

event: server.crashed
data: {"event_id":"evt_...","seq":10438,...}

: heartbeat
```

A `: heartbeat` comment arrives every 15s; if none arrives for 45s, reconnect
with exponential backoff. **The stream does not replay what you missed while
disconnected** — always backfill via `/events?since=<cursor>` on reconnect. Good
for a live dashboard; never your only ingestion path.

### 4.6 Webhooks

```bash
curl -X POST $BASE/api/monitoring/webhooks \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{
    "url": "https://monitor.internal/hooks/fluidmcp",
    "events": ["server.crashed", "server.unstable", "server.dependency_failed",
               "server.config_invalid", "server.restart_failed",
               "resource.memory_killed", "gateway.config_invalid"],
    "min_severity": "warning"
  }'
```

The response returns a generated `secret` **once** — store it. Delivery headers:

```
X-FMCP-Event: server.crashed
X-FMCP-Delivery: dlv_01J8X...
X-FMCP-Timestamp: 1756721642
X-FMCP-Gateway: gw-prod-1
X-FMCP-Signature: sha256=<hex>
```

**Always verify the signature** — the receiver is internet-reachable and its
payloads create incidents. The signed message is `"<timestamp>.<raw_body>"`:

```python
import hmac, hashlib, time

def verify(raw_body: bytes, signature: str, timestamp: str, secret: str) -> bool:
    if abs(time.time() - int(timestamp)) > 300:       # replay window
        return False
    expected = "sha256=" + hmac.new(
        secret.encode(), timestamp.encode() + b"." + raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

**Return 2xx fast.** FluidMCP retries 3× with backoff (2s/8s/32s) and
auto-disables a receiver after 10 consecutive failures (re-enable via
`/webhooks/{id}/enable`). Enqueue and process asynchronously. Deliveries are
**at-least-once** — deduplicate on `event_id`.

**URL restrictions (SSRF guard).** `https` only unless
`FMCP_WEBHOOK_ALLOW_INSECURE=true`; link-local and cloud-metadata ranges
(`169.254.0.0/16`) are blocked in every configuration; `FMCP_WEBHOOK_ALLOWLIST`
optionally restricts hosts.

### 4.7 `GET /api/monitoring/servers/{id}/diagnosis`

Call this when opening an incident. `summary` and `remediation` are written to
be pasted straight into a ticket.

```json
{
  "server_id": "pids",
  "state": "degraded",
  "diagnosis": {
    "failure_category": "db_connection_refused",
    "owner": "customer",
    "confidence": "high",
    "is_dependency_failure": true,
    "summary": "The MCP process is healthy but cannot reach its database or upstream host — every call fails at connection time.",
    "remediation": "The MCP server could not reach the SQL server at all. Verify the host and port, that the server is running, and that network/firewall rules permit the connection from the FluidMCP host.",
    "evidence": [
      { "source": "tool_error", "sample": "...", "matched": "ECONNREFUSED" }
    ]
  },
  "error_rate_5m": 0.83,
  "failing_tools": [...],
  "tool_stats": [...],
  "dependency_probe": { "dependency_failed": false, "consecutive_failures": 0 },
  "config_issues": {},
  "recent_crashes": [],
  "auto_restart": {
    "attempted": false,
    "restart_count": 0,
    "would_help": false,
    "reason": "Restarting will not fix this. The fault is outside the process — a credential, a configuration value, or an unreachable dependency — so FluidMCP does not restart automatically."
  }
}
```

**`auto_restart.would_help` should gate any retry UI you build.** It is `false`
for credentials, configuration, unreachable dependencies, upstream 5xx and rate
limiting — restarting changes nothing there and buries the cause. It is `true`
for genuine process faults and for connection-pool exhaustion, where a restart
really does clear the condition.

Evidence samples are redacted before return (see §10.2).

### 4.8 `GET /api/monitoring/uptime`

```
GET /api/monitoring/uptime?window=24h        # 1h | 24h | 7d | 30d
```

```json
{
  "window": "24h",
  "servers": [
    { "server_id": "pids", "uptime_pct": 97.42, "downtime_seconds": 2228,
      "degraded_seconds": 1180, "crash_count": 3, "restart_count": 3,
      "mttr_seconds": 742, "mtbf_seconds": 28800, "measured": true }
  ],
  "fleet": { "uptime_pct": 99.1, "total_crashes": 5, "servers_with_incidents": 2 }
}
```

`degraded_seconds` is tracked **separately** from downtime: a server that was up
but unusable is not uptime as far as a customer is concerned, and conflating
them makes the SLA number disputable. `measured: false` means no state
transitions were recorded in the window, so 100% is an assumption rather than a
measurement.

---

## 5. Consuming it from a monitoring system

### 5.1 Collection strategy

```
Webhook  (push, <1s)  ──►  instant incident creation
Poll /api/monitoring/health (30s)  ──►  reconciliation + "is the gateway alive?"
Poll /api/monitoring/events (30s)  ──►  gap-free backfill if a webhook dropped
```

### 5.2 The rule that matters most

> **A failed or stale poll is your highest-severity alert.**

Alert if `/health` is unreachable for 2 consecutive polls, **or** `generated_at`
is more than 3× your poll interval old.

Three distinct gateway failure modes, each needing its own alert:

| Mode | How you see it | Severity |
|---|---|---|
| Gateway **down** | Poll fails or times out | P1 |
| Gateway **up but misconfigured** | Reachable, `config.errors` non-empty | P1 |
| Gateway **restarted** | `boot_id` changed | P1 if no deploy was expected |

### 5.3 Minimal collector

```python
async def collect(base, token):
    headers = {"Authorization": f"Bearer {token}"}

    fleet = (await client.get(f"{base}/api/monitoring/health",
                              headers=headers)).json()

    # A changed boot_id means seq reset — re-sync rather than silently stalling.
    if fleet["boot_id"] != store.boot_id:
        store.reset_cursor(fleet["gateway_id"], fleet["boot_id"])

    batch = (await client.get(
        f"{base}/api/monitoring/events?since={store.cursor}&limit=500",
        headers=headers)).json()

    for event in batch["events"]:
        store.ingest(event)          # deduplicate on event_id
    store.cursor = batch["latest_seq"]

    return fleet
```

### 5.4 Event types

| Type | Severity | Meaning |
|---|---|---|
| `server.started` | info | Started successfully |
| `server.stopped` | info | Intentional stop or clean exit |
| `server.crashed` | critical | Process died unexpectedly |
| `server.restarting` | warning | Restart attempt beginning |
| `server.restarted` | info | Restart succeeded |
| `server.restart_failed` | critical | Restart failed, or max restarts reached |
| `server.unstable` | critical | ≥5 restarts in 10 min — crash loop |
| `server.recovered` | info | Back to healthy |
| `server.zombie` | critical | PID alive, HTTP unresponsive |
| `server.degraded` | warning | Tool error rate above threshold |
| `server.dependency_failed` | critical | Health probe says the dependency is down |
| `server.config_invalid` | critical | Missing/placeholder credentials, or bad command |
| `gateway.config_invalid` | critical | FluidMCP itself misconfigured |
| `resource.memory_warning` | warning | ≥90% of memory limit |
| `resource.memory_killed` | critical | Killed at ≥98% of limit |
| `resource.cpu_stuck` | warning | Pegged CPU for 3 consecutive cycles |
| `gateway.started` / `gateway.stopping` | info | Gateway lifecycle |

`GET /api/monitoring/event-types` returns this list from the running gateway, so
alert rules can be validated against reality rather than against this table.

### 5.5 `failure_category` values

`oom` · `segfault` · `resource_kill` · `cpu_stuck` · `command_not_found` ·
`bad_command` · `permission_denied` · `missing_dependency` ·
`missing_credentials` · `invalid_config` · `db_connection_refused` ·
`db_auth_failed` · `db_pool_exhausted` · `db_unavailable` ·
`db_firewall_blocked` · `db_not_accessible` · `db_resource_limit` ·
`tls_failure` · `upstream_auth_failed` · `upstream_5xx` · `upstream_timeout` ·
`rate_limited` · `unresponsive` · `unknown`

> **If a real failure classifies as `unknown`, report it.** It means that MCP's
> error text is not in the catalog. Send the exact error string so it can be
> added to
> [`failure_patterns.py`](../fluidmcp/cli/services/failure_patterns.py), or add
> it yourself via `FMCP_FAILURE_PATTERNS_FILE` (JSON):
>
> ```json
> { "patterns": [ { "regex": "specific error text",
>                   "category": "db_connection_refused",
>                   "owner": "customer",
>                   "remediation": "What the operator should do." } ],
>   "replace": false }
> ```

### 5.6 Exit codes

| Code | Label | Meaning |
|---|---|---|
| 0 | `clean_exit` | Normal |
| 1 | `generic_error` | Unhandled error |
| 126 | `permission_denied` | Not executable |
| 127 | `command_not_found` | Binary missing |
| 137 | `oom_killed` | OS killed it (likely OOM) |
| 139 | `segfault` | Segmentation fault |
| 143 | `sigterm_container` | Container runtime stop |
| -1 | `killed_by_fluidmcp` | Resource monitor kill |
| -9 | `sigkill` | Force-killed |
| -15 | `sigterm` | Graceful shutdown |

---

## 6. Alerting and dashboards

### 6.1 Alert rules

| Condition | Severity | Route | Why |
|---|---|---|---|
| `/health` unreachable ×2, or `generated_at` stale | **P1** | FluidMCP | Total outage; no webhooks will fire |
| `config.errors` non-empty | **P1** | FluidMCP | Misconfigured deploy — up but broken |
| `boot_id` changed unexpectedly | **P1** | FluidMCP | Gateway crashed and restarted |
| `boot_count` jumped >1 between polls | **P1** | FluidMCP | Gateway crash-looping |
| `state: failed` with restarts exhausted | **P1** | FluidMCP + customer | Down and not coming back |
| `stability: unstable` | **P1** | FluidMCP | Crash loop — one incident, not one per crash |
| `failure_owner: customer` | **P1** | **Customer team** | Only they can fix it; include `remediation` verbatim |
| `state: config_error` | **P1** | Customer team | Will never work until credentials are set |
| `state: degraded` > 5 min | **P2** | By `failure_owner` | Alive but failing calls |
| Any `failing_tools[].error_rate_5m > 0.5` | **P2** | By `failure_owner` | One endpoint broken inside a healthy server |
| `database.status != connected` | **P2** | FluidMCP | History is being lost right now |
| `event_loop_lag_ms > 250` sustained | **P2** | FluidMCP | Gateway wedging |
| `crashes_last_hour > 3` on one server | **P2** | FluidMCP | Chronic instability |
| `memory_trend: rising` + `memory_usage_pct > 85` | **P3** | FluidMCP | Predicts the next OOM |
| Single crash, auto-restart succeeded | **info** | Log only | FluidMCP handled it — do not page |

**Suppression rules that prevent alert fatigue:**

- Suppress `server.crashed` for 10 minutes after `server.unstable` fires for
  that server — a crash loop is one incident, not fifteen.
- Suppress all per-server alerts while the gateway itself is down.
- Auto-resolve on `server.recovered`.

### 6.2 Dashboard layout

**Gateway health strip** — always visible, top of every view:

- 🟢/🔴 **FluidMCP is up / down**, driven by poll success rather than any field
  in the response
- Uptime since `started_at`, `boot_count`, and a marker whenever `boot_id` changes
- Config validity badge — red, naming the offending keys, when `config.errors`
  is non-empty
- Database state, event-loop lag, `generated_at` freshness

Treat gateway-down as a distinct visual state that greys out the server grid. A
stale grid rendered as if live is worse than no grid — it reports every server
as last-known-good while the gateway is dead.

**Fleet overview:**

- Status tiles: total / running / degraded / config_error / failed / unstable
- Server grid: name, state pill, uptime, restarts (24h), error rate, memory trend
- Live event feed (SSE), severity-coloured

**Server detail:**

- State timeline (running / degraded / down bands over 24h)
- Memory and CPU sparklines with limit lines
- Per-tool error rates from `failing_tools`, sorted by rate
- Config issues panel — missing/placeholder key names
- Current diagnosis card (`summary` + `remediation` + evidence)
- Crash table and stderr tail with a filter box
- Restart button — operator action, confirm dialog, **hidden when
  `auto_restart.would_help` is `false`**

**Report view** (weekly, exportable):

- Uptime % per server vs target, with `degraded_seconds` shown separately
- Incident list with cause, owner, duration
- Failures split by `failure_owner` — the chart that ends "whose fault is it"
- Top recurring `failure_category` values with remediation status

Keep **degraded** visually distinct from **down** everywhere; conflating them is
what makes uptime numbers get disputed.

---

## 7. Configuration

Every variable has a working default. **None are required** for monitoring to
function.

```bash
# ── Detection ─────────────────────────────────────────────────────────
FMCP_HEALTH_CHECK_INTERVAL=30      # watchdog cycle, seconds
FMCP_HTTP_PING_TIMEOUT=10          # zombie detection threshold
FMCP_RESTART_STORM_THRESHOLD=5     # restarts per 10 min → unstable
FMCP_RESTART_TIMEOUT_S=60          # max time for one restart

# ── Resource limits ───────────────────────────────────────────────────
FMCP_DEFAULT_MEMORY_LIMIT_MB=0     # 0 = no limit
FMCP_MEMORY_WARN_PCT=90
FMCP_MEMORY_KILL_PCT=98
FMCP_CPU_WARN_PCT=90
FMCP_CPU_KILL_CYCLES=3

# ── Degradation (per-tool error rates) ────────────────────────────────
FMCP_DEGRADED_ERROR_RATE=0.5       # per-tool rate that trips degraded
FMCP_DEGRADED_MIN_SAMPLES=5        # minimum calls before the rate is trusted
FMCP_ERROR_WINDOW_SECONDS=300      # rolling window
FMCP_RECOVERY_STREAK=5             # consecutive successes to clear degraded

# ── Events ────────────────────────────────────────────────────────────
FMCP_EVENT_RETENTION_DAYS=30       # MongoDB TTL on mcp_events
FMCP_EVENT_BUFFER_SIZE=1000        # in-memory ring size

# ── Webhooks ──────────────────────────────────────────────────────────
FMCP_WEBHOOK_TIMEOUT=10
FMCP_WEBHOOK_MAX_RETRIES=3
FMCP_WEBHOOK_ALLOWLIST=            # comma-separated host globs; empty = any
FMCP_WEBHOOK_ALLOW_INSECURE=false  # true permits http:// and private IPs

# ── Classification ────────────────────────────────────────────────────
FMCP_FAILURE_PATTERNS_FILE=        # JSON file of extra patterns

# ── Gateway identity and config policy ────────────────────────────────
FMCP_GATEWAY_ID=                   # names this deployment; set it in production
FMCP_STRICT_CONFIG=false           # true = refuse to start on invalid config
FMCP_EVENT_LOOP_LAG_WARN_MS=250
FMCP_REQUIRE_PERSISTENCE=false     # /health/ready 503s when the DB is down
```

### Per-server configuration

```json
{
  "id": "pids",
  "name": "PIDS Analytics MCP",
  "command": "python3",
  "args": ["/app/pids_server.py"],
  "env": { "DB_HOST": "...", "DB_PASSWORD": "..." },
  "required_env": ["DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME"],
  "strict_config": false,
  "health_probe": {
    "tool": "get_latest_alarms",
    "args": { "since_id": 0, "limit": 1 },
    "interval_seconds": 60,
    "timeout_seconds": 25,
    "failure_threshold": 2
  },
  "restart_on_dependency_failure": false,
  "restart_policy": "on-failure",
  "max_restarts": 3,
  "memory_limit_mb": 512
}
```

`required_env` is what powers pre-flight validation — declare it for every
server that needs credentials, or missing values are only caught at first use.

---

## 8. Production deployment

**Nothing new is required.** The existing `Dockerfile` and `entrypoint.sh` work
unchanged, no new environment variables are mandatory, and the MongoDB
collections and indexes are created automatically by `init_db()`, which already
runs on the production startup path.

See [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md) for the deployment procedure
itself.

### Recommended, not required

| Setting | Why |
|---|---|
| `FMCP_GATEWAY_ID=<deployment-name>` | Without it, payloads fall back to `RAILWAY_SERVICE_NAME` or `"fluidmcp"`. Set it so a monitoring system can distinguish deployments. |
| `FMCP_BEARER_TOKEN` (already required) | Generate with `openssl rand -hex 32`. Must be set explicitly — an auto-generated token regenerates on restart and breaks authentication. |
| MongoDB attached | Without it, crash history, events and uptime history are lost on every restart. `/health` reports this as a warning. |
| `--require-persistence` | Fail fast instead of silently degrading to in-memory. |

### What monitoring adds to MongoDB

Created automatically on first connect:

| Collection | Indexes | Retention |
|---|---|---|
| `fluidmcp_events` | `(boot_id, seq)` unique, `(server_id, timestamp)`, `(severity, timestamp)` | TTL `FMCP_EVENT_RETENTION_DAYS` (30d) |
| `fluidmcp_gateway_boots` | `boot_id` unique, `(gateway_id, started_at)` | TTL 90d |
| `fluidmcp_state_transitions` | `(server_id, timestamp)` | TTL 90d |
| `fluidmcp_webhooks` | `id` unique | none |

All bounded by TTL indexes, so storage does not grow without limit.

### Operational characteristics

- Monitoring runs in-process; there is no extra container or sidecar.
- Event persistence is offloaded to a background worker with a bounded queue, so
  a slow database never blocks a health check or a restart.
- Webhook delivery is fire-and-forget on a bounded queue; a dead receiver cannot
  back-pressure the watchdog.
- Every emission path is exception-guarded: **a monitoring failure can never
  prevent a server restart.**

---

## 9. Testing and acceptance

### 9.1 Automated

```bash
# Unit + API tests
pytest tests/test_monitoring.py tests/test_monitoring_api.py -q

# End-to-end: starts a real gateway, breaks a real MCP's database mid-flight,
# and asserts the reported diagnosis. ~100s.
bash tests/manual/monitoring/live_test.sh 8123
```

[`tests/manual/monitoring/fake_sql_mcp.py`](../tests/manual/monitoring/fake_sql_mcp.py)
is an MCP whose "database" can be broken via flag files **without restarting the
process** — the only way to test the dependency-failure path honestly.

### 9.2 Acceptance checklist

Run this against a real deployment before handing monitoring to anyone.

#### A. Gateway is watched at all

```bash
curl -s $BASE/health | jq '{status, boot_id, boot_count, config}'
```

- [ ] `boot_id` present — **write it down**
- [ ] `config.valid` is `true`, or `config.errors` names something expected
- [ ] `/health/ready` returns `200`

Then **stop the gateway**:

- [ ] Poll fails → dashboard shows FluidMCP **down**, not "all healthy"
- [ ] A **P1** fires within two poll intervals

Restart it:

- [ ] `boot_id` **changed** → collector logged "gateway restarted"
- [ ] `boot_count` incremented
- [ ] Event cursor reset, with no events double-counted

> The most important step. Everything else assumes the gateway is reachable;
> only this covers the case where it is not.

#### B. Fleet rollup reflects reality

- [ ] Every expected MCP appears, with the expected state
- [ ] `summary` counts add up to `total`
- [ ] Response returns in well under a second

#### C. A real crash is caught, classified, restarted

```bash
PID=$(curl -s $BASE/api/monitoring/health | jq -r '.servers[0].pid')
kill -9 $PID
```

Within ~2× `FMCP_HEALTH_CHECK_INTERVAL`:

- [ ] `server.crashed` in the event feed with `exit_label: "sigkill"`
- [ ] `server.restarting` then `server.restarted` follow
- [ ] Server back to `running`, `restart_count` incremented
- [ ] Webhook delivered and its HMAC verified

#### D. A broken dependency is caught — the important one

Break the dependency **without touching the process** — block the database port,
revoke the credential, or stop the upstream:

```bash
sudo iptables -A OUTPUT -p tcp --dport 1433 -j REJECT
```

Call the affected tool 5+ times, wait one monitor cycle:

- [ ] `process_state` still `running` — the process is fine
- [ ] `state` is `degraded`
- [ ] `failing_tools` names the specific tool
- [ ] `failure_category` is a `db_*` / `upstream_*` value, **not `unknown`**
- [ ] `failure_owner` is `customer`
- [ ] `diagnosis` gives a `summary` and `remediation` you would send to the customer
- [ ] `auto_restart.would_help` is `false`, and no restart is offered

Undo the break, call the tool ~6 more times:

- [ ] `success_streak` climbs, `state` returns to `running`
- [ ] `server.recovered` emitted; incident auto-resolves

#### E. Missing credentials caught before first use

Register an MCP with a missing or placeholder credential and start it:

- [ ] `server.config_invalid` emitted **at start**, not at first tool call
- [ ] `config_issues` names the keys
- [ ] **No credential values anywhere** — grep the response for the real secret
- [ ] `failure_owner: customer`, remediation names the keys to set

#### F. Event delivery is lossless

- [ ] Record cursor, generate 3 events, poll with `since=<cursor>` → exactly 3
- [ ] Poll again with the new cursor → `returned: 0`
- [ ] `seq` strictly ascending, no gaps
- [ ] Stop the receiver, generate events, restart, backfill → nothing lost
- [ ] Same `event_id` twice → deduplicated

#### G. Alert routing

- [ ] `failure_owner: customer` reaches the customer path with `remediation` verbatim
- [ ] Everything else reaches the FluidMCP path
- [ ] A flapping server produces **one** `server.unstable` incident
- [ ] A single crash that auto-restarted does **not** page anyone

### 9.3 What to send when something is wrong

```bash
curl -s $BASE/api/monitoring/gateway                        > gateway.json
curl -s $BASE/api/monitoring/health                         > fleet.json
curl -s "$BASE/api/monitoring/events?limit=200"             > events.json
curl -s $BASE/api/monitoring/servers/<id>/diagnosis         > diagnosis.json
curl -s "$BASE/api/servers/<id>/stderr?lines=100"           > stderr.json
```

Check `stderr.json` for credentials before sharing — the others redact by
design, but raw stderr is whatever the MCP printed.

---

## 10. Implementation notes

### 10.1 Source map

| File | Purpose |
|---|---|
| [`models/events.py`](../fluidmcp/cli/models/events.py) | Event enum, severity, envelope, wire format |
| [`services/event_bus.py`](../fluidmcp/cli/services/event_bus.py) | `seq` assignment, ring buffer, async persistence, SSE fan-out |
| [`services/failure_patterns.py`](../fluidmcp/cli/services/failure_patterns.py) | Regex catalog + owner attribution (data only) |
| [`services/failure_classifier.py`](../fluidmcp/cli/services/failure_classifier.py) | `classify_text`, `classify_exit`, `diagnose` |
| [`services/config_validator.py`](../fluidmcp/cli/services/config_validator.py) | Pre-flight credential validation |
| [`services/tool_error_tracker.py`](../fluidmcp/cli/services/tool_error_tracker.py) | Per-`(server, tool)` error rates, degraded/recovered |
| [`services/dependency_probe.py`](../fluidmcp/cli/services/dependency_probe.py) | Active `health_probe` execution |
| [`services/webhook_dispatcher.py`](../fluidmcp/cli/services/webhook_dispatcher.py) | HMAC delivery, retry, SSRF guards, auto-disable |
| [`services/gateway_info.py`](../fluidmcp/cli/services/gateway_info.py) | `boot_id`, config validity, self-resources, loop lag |
| [`services/server_manager.py`](../fluidmcp/cli/services/server_manager.py) | `MCPHealthMonitor`, restart policy, event emission |
| [`api/monitoring.py`](../fluidmcp/cli/api/monitoring.py) | All `/api/monitoring/*` endpoints |

### 10.2 Credential handling

Three layers, because credentials otherwise escape by three different routes:

1. **API responses mask env values.** `GET /api/servers` and
   `GET /api/servers/{id}` return `"***REDACTED***"` in place of every value,
   keeping the keys. A bearer token grants operational access, not the right to
   read every MCP's database password.

   A client that reads a config and PUTs it back sends the mask, not the secret.
   `update_server` therefore restores the stored value for any key still
   carrying the mask, so a round-trip cannot wipe credentials. A genuinely
   changed value is written through normally.

2. **Error text is redacted before it is stored or pushed.** MCP servers
   routinely echo connection strings (`postgres://app:hunter2@db/prod`), and
   monitoring events travel further than logs — into an external store, a Slack
   channel, a ticket. `redact_secrets()` scrubs URL userinfo, credential-named
   `key=value` pairs, provider key prefixes, bearer/basic values and JWTs.

   Classification runs on the **raw** text and only the redacted form is stored,
   so redaction never costs detection accuracy.

3. **Gateway secrets are stripped from MCP subprocesses.** An MCP server is
   third-party code; it has no business reading the gateway's own bearer token
   or database URI. `FMCP_BEARER_TOKEN`, `MONGODB_URI`, `GITHUB_TOKEN`, S3 keys
   and similar are removed from every child environment.

Config validation reports **key names only** — never values.

### 10.3 Environment variable precedence

**Per-server configuration wins over the gateway's own environment.** The
gateway environment is inherited as a base, so variables a server does not
define (`PATH`, `HOME`, proxy settings, deploy-time credentials) still reach it,
but anything the server declares takes precedence.

This was previously reversed, which meant a variable present in the gateway
environment silently overrode per-server config — accepted by the API, stored,
returned by `GET`, then discarded at spawn. Two MCP servers could not use
different values for the same variable, which defeats the point of a
multi-server orchestrator.

Placeholder values are never injected: a real value inherited from the
environment is better than a literal `<your-key>`, and the skip is logged.

### 10.4 Design rules

- **Monitoring must never break recovery.** Every emission and bookkeeping call
  in the restart path is exception-guarded. A missing metric costs an accurate
  graph; a skipped restart costs an outage. Enforced by tests that fail if the
  guards are removed.
- **Classify before redacting.** Redaction is lossy and can remove the token a
  pattern matches on.
- **Warn, do not block, on config.** Blocking a start by default turns
  monitoring into an outage. `strict_config` is opt-in.
- **Do not auto-restart dependency failures.** A restart loop on a credentials
  problem hides the fault. Opt-in per server.
- **Cursor on `seq`, never timestamps.** Clock skew and same-millisecond writes
  cause silent event loss.

### 10.5 Known limitations

- **A crash-looping gateway that never binds serves no `/health`.** The only
  external evidence is absence of heartbeat, which is why the stale-poll alert
  is load-bearing. Mitigated by writing a boot record to MongoDB before any
  fail-fast exit, so the history explains the gap once the database is reachable.
- **stdio-transport servers cannot be probed.** A probe would contend with the
  gateway's own pipe, so `health_probe` applies to HTTP/SSE transports; stdio
  servers rely on passive tool-error tracking.
- **Uptime before the first recorded transition is an assumption.** Reported as
  `measured: false`.
- **In-memory mode loses all history on restart.** Events, crash history and
  uptime are meaningless without MongoDB. `/health` reports this as a warning.

---

## 11. Outstanding issues found during this work

Unrelated to monitoring, but surfaced while building and testing it. Recorded
here so they are not lost; none is fixed.

### FluidMCP cannot connect to a non-TLS MongoDB

[`database.py`](../fluidmcp/cli/repositories/database.py) always passes
`tlsAllowInvalidCertificates` to `AsyncIOMotorClient`. In the pinned PyMongo
version, passing any `tls*` option implies `tls=True`, so the client attempts a
TLS handshake against a plain MongoDB and fails. Reproduced against `mongo:7`:

```
mongod:   "SSL handshake received but server is started without SSL support"
fluidmcp: "SSL handshake failed: [SSL: UNEXPECTED_EOF_WHILE_READING]"
```

Managed MongoDB (Railway, Atlas) uses TLS, so **production is unaffected** — but
local development against a plain `mongod` is impossible. Fix: pass the `tls*`
kwargs only when TLS is actually intended, gated on the URI scheme or an
explicit `FMCP_MONGODB_TLS` flag. Left alone because it touches the production
database path.

### `POST /api/servers` payload in CLAUDE.md is wrong

CLAUDE.md documents `{"server_id": ..., "config": {...}}`. The endpoint accepts
a **flat** object with `id`. Posting the documented shape returns
`{"detail": "Server id is required"}`.

### Pre-existing test failures

On a clean checkout, before any change in this work:

- `tests/test_validators.py` fails to import (`NameError: AddServerFromGitHubRequest`)
- `tests/test_serve_api.py` and `tests/test_serve_e2e.py` hang
- 8 tests fail and 1 errors across `test_debug_api_crashes_stderr`,
  `test_github_integration_api`, `test_integration`, `test_run_servers`,
  `test_llm_launcher`

### Test hygiene fixed in passing

`test_debug_aggregator.py` and `test_debug_api_crashes_stderr.py` used the
deprecated `asyncio.get_event_loop()` pattern, which only works when an earlier
test happens to leave a current event loop on the main thread. The same failure
reproduces on a clean checkout by running any pre-existing async test file
first:

```bash
pytest tests/test_crash_root_cause.py tests/test_debug_aggregator.py
# RuntimeError: There is no current event loop in thread 'MainThread'
```

Replaced seven call sites with `asyncio.run()`, which carries no ordering
dependency. This removed 3 of the previously-failing tests.
